"""Optional ALSA microphone preamp controls; opening this module never changes gain.

PipeWire/Pulse volume is not necessarily the microphone's separate preamp.
Use the selected source's ALSA card and active port, never a default sound card.
No root helper, audio-server restart, or configuration rewrite is needed.
"""
from __future__ import annotations

import ctypes as C
from functools import lru_cache
import re


class GainUnavailable(RuntimeError):
    pass


def source_port(source):
    port = source.get('active_port') or ''
    return str(port.get('name', '')) if isinstance(port, dict) else str(port)


def source_card(source):
    props = source.get('properties', {})
    if (str(source.get('name', '')).endswith('.monitor') or
            props.get('device.class') == 'monitor' or
            source.get('monitor_of_sink') not in (None, 4294967295, '4294967295')):
        return None
    for key in ('api.alsa.pcm.card', 'alsa.card', 'api.alsa.card'):
        value = str(props.get(key, ''))
        if re.fullmatch(r'\d{1,3}', value):
            return int(value)
    return None


def source_context(source):
    return source.get('name'), source_card(source), source_port(source)


def control_kind(name, direction):
    """Explicit input names only. A plain playback 'Mic' is usually loopback."""
    words = name.casefold()
    if re.search(r'\b(speaker|headphone|output|loopback|sidetone|monitor|playback)\b', words):
        return None
    input_name = re.search(r'\b(mic|microphone|capture|input|adc)\b', words)
    if input_name and re.search(r'\b(boost|preamp|gain)\b', words):
        return 'boost'
    if direction == 'capture' and (input_name or words == 'digital'):
        return 'capture'
    return None


def controls_for_port(controls, port):
    """Filter jack-specific boosts; never apply a front-mic fader to a rear jack."""
    qualifiers = ('front', 'rear', 'internal', 'headset', 'headphone', 'dock')
    port_words = set(re.findall(r'[a-z]+', port.casefold()))
    if 'headphone' in port_words:
        port_words.add('headset')
    is_mic = bool(port_words & {'mic', 'microphone'})
    choices = []
    for control in controls:
        words = set(re.findall(r'[a-z]+', control['name'].casefold()))
        specific = words.intersection(qualifiers)
        if specific and not specific.intersection(port_words):
            continue
        if port and not is_mic and control['kind'] == 'boost' and words & {'mic', 'microphone'}:
            continue
        choices.append(control)
    boosts = [c for c in choices if c['kind'] == 'boost']
    # If a jack-specific boost exists, the unqualified 'Mic Boost' generally
    # belongs to a different input. Keep only the explicit port match.
    matched = [c for c in boosts if set(re.findall(r'[a-z]+', c['name'].casefold())).intersection(qualifiers)]
    return matched or boosts or [c for c in choices if c['kind'] == 'capture']


def gain_label(db, raw):
    if db is None:
        return f'Step {raw}'
    if db <= -9999999:  # SND_CTL_TLV_DB_GAIN_MUTE
        return '−∞ dB'
    return f'{db / 100:+g} dB' if db else '0 dB'


@lru_cache(maxsize=1)
def alsa():
    try:
        lib = C.CDLL('libasound.so.2')
    except OSError as error:
        raise GainUnavailable('Hardware gain needs the ALSA library (libasound).') from error
    ptr, integer, long = C.c_void_p, C.c_int, C.c_long
    signatures = {
        'snd_strerror': (C.c_char_p, [integer]),
        'snd_mixer_open': (integer, [C.POINTER(ptr), integer]),
        'snd_mixer_close': (integer, [ptr]),
        'snd_mixer_attach': (integer, [ptr, C.c_char_p]),
        'snd_mixer_selem_register': (integer, [ptr, ptr, ptr]),
        'snd_mixer_load': (integer, [ptr]),
        'snd_mixer_first_elem': (ptr, [ptr]),
        'snd_mixer_elem_next': (ptr, [ptr]),
        'snd_mixer_selem_get_name': (C.c_char_p, [ptr]),
        'snd_mixer_selem_get_index': (C.c_uint, [ptr]),
        'snd_mixer_selem_is_active': (integer, [ptr]),
        'snd_mixer_get_hctl': (integer, [ptr, C.c_char_p, C.POINTER(ptr)]),
        'snd_hctl_ctl': (ptr, [ptr]),
        'snd_ctl_card_info_malloc': (integer, [C.POINTER(ptr)]),
        'snd_ctl_card_info_free': (None, [ptr]),
        'snd_ctl_card_info': (integer, [ptr, ptr]),
        'snd_ctl_card_info_get_id': (C.c_char_p, [ptr]),
        'snd_ctl_card_info_get_longname': (C.c_char_p, [ptr]),
    }
    for direction in ('capture', 'playback'):
        prefix = 'snd_mixer_selem_'
        signatures.update({
            prefix + f'has_{direction}_volume': (integer, [ptr]),
            prefix + f'has_{direction}_channel': (integer, [ptr, integer]),
            prefix + f'get_{direction}_volume_range': (integer, [ptr, C.POINTER(long), C.POINTER(long)]),
            prefix + f'get_{direction}_volume': (integer, [ptr, integer, C.POINTER(long)]),
            prefix + f'ask_{direction}_vol_dB': (integer, [ptr, long, C.POINTER(long)]),
            prefix + f'set_{direction}_volume': (integer, [ptr, integer, long]),
        })
    for name, (result, args) in signatures.items():
        function = getattr(lib, name)
        function.restype, function.argtypes = result, args
    return lib


class Mixer:
    def __init__(self, card):
        if type(card) is not int or not 0 <= card <= 999:
            raise GainUnavailable('The microphone has no valid ALSA card.')
        self.lib = alsa()
        self.handle = C.c_void_p()
        self.card = card
        self.device = f'hw:{card}'.encode('ascii')

    def checked(self, result):
        if result < 0:
            reason = self.lib.snd_strerror(result).decode(errors='replace')
            raise GainUnavailable('Cannot access microphone hardware gain: ' + reason)
        return result

    def __enter__(self):
        try:
            self.checked(self.lib.snd_mixer_open(C.byref(self.handle), 0))
            self.checked(self.lib.snd_mixer_attach(self.handle, self.device))
            self.checked(self.lib.snd_mixer_selem_register(self.handle, None, None))
            self.checked(self.lib.snd_mixer_load(self.handle))
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        if self.handle:
            self.lib.snd_mixer_close(self.handle)
            self.handle = C.c_void_p()

    def card_identity(self):
        hctl, info = C.c_void_p(), C.c_void_p()
        self.checked(self.lib.snd_mixer_get_hctl(self.handle, self.device, C.byref(hctl)))
        self.checked(self.lib.snd_ctl_card_info_malloc(C.byref(info)))
        try:
            self.checked(self.lib.snd_ctl_card_info(self.lib.snd_hctl_ctl(hctl), info))
            return tuple((getattr(self.lib, 'snd_ctl_card_info_get_' + field)(info) or b'').decode(errors='replace')
                         for field in ('id', 'longname'))
        finally:
            self.lib.snd_ctl_card_info_free(info)

    def function(self, verb, direction, suffix):
        return getattr(self.lib, f'snd_mixer_selem_{verb}_{direction}_{suffix}')

    def entries(self):
        element = self.lib.snd_mixer_first_elem(self.handle)
        while element:
            if self.lib.snd_mixer_selem_is_active(element):
                name = self.lib.snd_mixer_selem_get_name(element).decode(errors='replace')
                for direction in ('capture', 'playback'):
                    kind = control_kind(name, direction)
                    if not kind or not self.function('has', direction, 'volume')(element):
                        continue
                    low, high = C.c_long(), C.c_long()
                    self.checked(self.function('get', direction, 'volume_range')(element, C.byref(low), C.byref(high)))
                    if high.value <= low.value:
                        continue
                    channels = []
                    for channel in range(32):
                        if self.function('has', direction, 'channel')(element, channel):
                            value = C.c_long()
                            self.checked(self.function('get', direction, 'volume')(element, channel, C.byref(value)))
                            channels.append((channel, value.value))
                    if channels:
                        yield element, dict(name=name, index=self.lib.snd_mixer_selem_get_index(element),
                                            direction=direction, kind=kind, minimum=low.value,
                                            maximum=high.value, channels=channels)
                    # Common controls can appear in both directions; show them once.
                    break
            element = self.lib.snd_mixer_elem_next(element)

    def steps(self, element, control):
        low, high = control['minimum'], control['maximum']
        count = min(512, high - low)
        values = {low + round(i * (high - low) / count) for i in range(count + 1)}
        values.update(value for _, value in control['channels'])
        result = []
        for value in sorted(values):
            db = C.c_long()
            status = self.function('ask', control['direction'], 'vol_dB')(element, value, C.byref(db))
            result.append((value, db.value if status >= 0 else None))
        return result

    def write(self, element, control, target):
        previous = control['channels']
        delta = target - max(value for _, value in previous)
        written = []
        try:
            for channel, old in previous:
                value = max(control['minimum'], min(control['maximum'], old + delta))
                if value != old:
                    self.checked(self.function('set', control['direction'], 'volume')(element, channel, value))
                    written.append((channel, old))
        except GainUnavailable:
            for channel, old in written:
                self.function('set', control['direction'], 'volume')(element, channel, old)
            raise


def control_key(control):
    return control['name'], control['index'], control['direction']


def inspect_source(source):
    result = {'source': source.get('name') if source else None, 'controls': [], 'message': ''}
    if not source:
        result['message'] = 'Connect a microphone to adjust its gain.'
        return result
    card = source_card(source)
    if card is None:
        result['message'] = 'This input does not expose ALSA hardware gain. Use microphone volume above.'
        return result
    try:
        with Mixer(card) as mixer:
            card_id = mixer.card_identity()
            entries = list(mixer.entries())
            allowed = {control_key(c) for c in controls_for_port([c for _, c in entries], source_port(source))}
            for element, control in entries:
                if control_key(control) not in allowed:
                    continue
                control.update(card=card, card_identity=card_id, context=source_context(source),
                               steps=mixer.steps(element, control), value=max(v for _, v in control['channels']))
                result['controls'].append(control)
    except (GainUnavailable, OSError) as error:
        result['controls'] = []
        result['message'] = str(error)
        return result
    if not result['controls']:
        result['message'] = 'No separate boost control is exposed for this input. Lower microphone volume above, or use the microphone’s physical gain control if available.'
    elif result['controls'][0]['kind'] == 'capture':
        result['message'] = 'Hardware capture gain. This may also change the microphone volume above. Lower it if speech distorts.'
    else:
        result['message'] = 'Lower boost if speech sounds loud or distorted. Choose the lowest level that makes your voice clear.'
    return result


def apply_gain(source, expected, target):
    if source_context(source) != tuple(expected['context']):
        raise ValueError('The microphone input changed. Refresh before adjusting gain.')
    if type(target) is not int or not expected['minimum'] <= target <= expected['maximum']:
        raise ValueError('Choose a gain within the microphone’s hardware range.')
    with Mixer(source_card(source)) as mixer:
        if mixer.card_identity() != tuple(expected['card_identity']):
            raise ValueError('The sound card changed. Refresh before adjusting gain.')
        entries = list(mixer.entries())
        allowed = {control_key(c) for c in controls_for_port([c for _, c in entries], source_port(source))}
        for element, current in entries:
            if control_key(current) != control_key(expected) or control_key(current) not in allowed:
                continue
            if (current['minimum'], current['maximum']) != (expected['minimum'], expected['maximum']):
                raise ValueError('The microphone gain range changed. Refresh devices.')
            mixer.write(element, current, target)
            return
    raise ValueError('That microphone gain control is no longer available. Refresh devices.')
