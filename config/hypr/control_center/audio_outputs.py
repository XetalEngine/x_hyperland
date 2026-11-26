"""Connected HDMI/DisplayPort choices, including ports outside the active profile."""
from __future__ import annotations

import time


def named(value):
    return str(value.get('name', '')) if isinstance(value, dict) else str(value or '')


def entries(value):
    if isinstance(value, dict):
        return {name: {**item, 'name': name} for name, item in value.items()}
    return {item['name']: item for item in value or []}


def card_identity(card):
    return card['index'], str(card.get('properties', {}).get('object.serial', ''))


def on_card(sink, card):
    name = sink.get('properties', {}).get('device.name')
    if name:
        return name == card['name']
    return str(sink.get('card', '')) == str(card['index'])


def connected_monitor(port):
    props = port.get('properties', {})
    if not (str(port.get('type', '')).lower() == 'hdmi'
            or props.get('port.type') == 'hdmi' or port['name'].startswith('hdmi-output-')):
        return False
    availability = port.get('availability')
    if availability in (False, 'no', 'not available', 'unavailable'):
        return False
    return availability in (True, 'yes', 'available') or bool(props.get('device.product.name'))


def profile_for_port(card, port):
    profiles = entries(card.get('profiles', {}))
    current = named(card.get('active_profile'))
    inputs = {part for part in current.split('+') if part.startswith('input:')}
    candidates = []
    for name in port.get('profiles', []):
        profile = profiles.get(name, {})
        if (profile.get('sinks', 0) < 1
                or profile.get('available') in (False, 'no', 'not available', 'unavailable')):
            continue
        # Switching an output must not silently disable this card's microphone.
        if not inputs.issubset(set(name.split('+'))):
            continue
        candidates.append((name == current, profile.get('priority', 0), name))
    return max(candidates)[2] if candidates else None


def choices(cards, sinks):
    """Read-only inventory. Keep real sinks for USB, Bluetooth and virtual audio."""
    result = [dict(sink) for sink in sinks]
    for card in cards:
        for port in entries(card.get('ports', {})).values():
            if not connected_monitor(port) or not profile_for_port(card, port):
                continue
            product = port.get('properties', {}).get('device.product.name', '')
            description = port.get('description', port['name'])
            title = f'{product} — {description}' if product else description
            active = next((sink for sink in sinks if on_card(sink, card)
                           and named(sink.get('active_port')) == port['name']), None)
            choice = dict(active) if active else {'name': 'monitor:' + card['name'] + ':' + port['name']}
            choice.update(description=title,
                          tooltip=title + '\n' + card.get('properties', {}).get('device.description', card['name']),
                          monitor_route={'card': card['name'], 'identity': card_identity(card),
                                         'port': port['name'], 'product': product})
            if active:
                result[next(i for i, item in enumerate(result) if item['name'] == active['name'])] = choice
            else:
                result.append(choice)
    return result


def current_route(route, listing):
    card = next((item for item in listing('card') if item['name'] == route['card']
                 and card_identity(item) == tuple(route['identity'])), None)
    if card is None:
        raise ValueError('That audio device disconnected. Refresh devices.')
    port = entries(card.get('ports', {})).get(route['port'])
    if not port or not connected_monitor(port):
        raise ValueError('That monitor disconnected. Refresh devices.')
    if port.get('properties', {}).get('device.product.name', '') != route['product']:
        raise ValueError('The monitor on that connection changed. Refresh devices.')
    return card, port


def wait_for_output(route, profile, listing, *, previous_profile=None, require_active_port=False, timeout=4):
    deadline = time.monotonic() + timeout
    while True:
        card, _ = current_route(route, listing)
        active = named(card.get('active_profile'))
        if active == profile:
            candidates = [sink for sink in listing('sink') if on_card(sink, card)
                          and route['port'] in entries(sink.get('ports', []))]
            selected = next((sink for sink in candidates
                             if named(sink.get('active_port')) == route['port']), None)
            if selected:
                return selected
            if candidates and not require_active_port:
                return candidates[0]
        elif active != previous_profile:
            raise ValueError('The audio configuration changed while switching outputs. Refresh devices.')
        if time.monotonic() >= deadline:
            raise RuntimeError('The monitor audio output did not become ready. Try again or reconnect the display.')
        time.sleep(.1)


def activate(choice, listing, command, *, on_ready=None):
    """Prepare the chosen monitor; only an explicit selection calls this function."""
    route = choice['monitor_route']
    card, port = current_route(route, listing)
    profile = profile_for_port(card, port)
    if not profile:
        raise ValueError('That monitor audio output is unavailable. Refresh devices.')
    previous_profile = named(card.get('active_profile'))
    changed = profile != previous_profile
    try:
        if changed:
            command('set-card-profile', card['name'], profile)
        sink = wait_for_output(route, profile, listing, previous_profile=previous_profile)
        if named(sink.get('active_port')) != route['port']:
            command('set-sink-port', sink['name'], route['port'])
            sink = wait_for_output(route, profile, listing, require_active_port=True)
        if on_ready is not None:
            on_ready(sink)
        return sink
    except (ValueError, RuntimeError) as error:
        if changed:
            # Roll back our own failed activation, never a replacement card or
            # a profile another audio controller selected in the meantime.
            current = next((item for item in listing('card') if item['name'] == card['name']
                            and card_identity(item) == card_identity(card)), None)
            if current and named(current.get('active_profile')) == profile:
                try:
                    command('set-card-profile', card['name'], previous_profile)
                except RuntimeError as restore_error:
                    raise RuntimeError(str(error) + ' The previous output could not be restored: '
                                       + str(restore_error)) from error
        raise
