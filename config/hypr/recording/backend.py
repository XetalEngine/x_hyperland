"""Wayland capture and recoverable MP4 publication; no global audio changes."""
import hashlib
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import string
import subprocess
import sys
import tempfile
import time
from datetime import datetime

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT/'settings.json'
DEFAULTS = dict(fps=64, audio='desktop', quality='high', encoder='auto', directory='',
                filename='Screen-recording-{date}_{time}')


def recording_name(pattern, monitor='DP-1', now=None):
    """Expand only documented tokens; a template can never name another folder."""
    now = now or datetime.now()
    tokens = {'date': now.strftime('%Y-%m-%d'), 'time': now.strftime('%H-%M-%S'),
              'year': now.strftime('%Y'), 'month': now.strftime('%m'), 'day': now.strftime('%d'),
              'hour': now.strftime('%H'), 'minute': now.strftime('%M'), 'second': now.strftime('%S'),
              'monitor': re.sub(r'[^\w.-]', '_', monitor)[:64] or 'display'}
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError('Enter a recording filename format.')
    try:
        for _, field, spec, conversion in string.Formatter().parse(pattern):
            if field is not None and (field not in tokens or spec or conversion):
                raise ValueError('Use filename tokens such as {date}, {time} and {monitor}.')
        name = pattern.format_map(tokens).strip()
    except (KeyError, ValueError) as error:
        raise ValueError('Use filename tokens such as {date}, {time} and {monitor}.') from error
    if any(ord(c) < 32 or c in '/\\' for c in name) or name in ('.', '..') or len(name.encode()) > 200:
        raise ValueError('Use a filename of up to 200 bytes, without folders or control characters.')
    return name if name.lower().endswith('.mp4') else name+'.mp4'


def publish_movie(movie, destination):
    """Reserve each final name atomically, even when two captures share a name."""
    for number in range(10000):
        target = destination if not number else destination.with_name(f'{destination.stem} ({number}){destination.suffix}')
        try:
            os.link(movie, target)
            return target
        except FileExistsError:
            continue
    raise RuntimeError('Too many recordings use this name. Choose another filename format.')


def validate(value):
    if not isinstance(value, dict) or set(value)-set(DEFAULTS):
        raise ValueError('Invalid recording preferences.')
    result = {**DEFAULTS, **value}
    if type(result['fps']) is not int or not 1 <= result['fps'] <= 240:
        raise ValueError('Choose a frame rate from 1 to 240 FPS.')
    for key, choices in [('audio', ('desktop', 'microphone', 'off')),
                         ('quality', ('high', 'balanced', 'small')),
                         ('encoder', ('auto', 'software'))]:
        if result[key] not in choices:
            raise ValueError('Invalid recording '+key+'.')
    directory = result['directory']
    if not isinstance(directory, str) or any(c in directory for c in '\x00\r\n'):
        raise ValueError('Choose a valid recordings folder.')
    if directory and not Path(directory).expanduser().is_absolute():
        raise ValueError('Choose an absolute recordings folder.')
    recording_name(result['filename'])
    return result


def load(path=SETTINGS):
    raw = path.read_bytes() if path.exists() else b''
    return validate(json.loads(raw) if raw else {}), hashlib.sha256(raw).hexdigest()


def save(value, expected, path=SETTINGS):
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent/'.settings.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _save(value, expected, path)


def _save(value, expected, path):
    value = validate(value)
    if load(path)[1] != expected:
        raise ValueError('Recording preferences changed elsewhere. Reload before saving.')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.recording-settings-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2); stream.write('\n')
            stream.flush(); os.fsync(stream.fileno())
        if load(path)[1] != expected:
            raise ValueError('Recording preferences changed elsewhere. Reload before saving.')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return load(path)


def run(argv, timeout=5):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or f'{argv[0]} failed').strip()[-700:])
    return result.stdout.strip()


def videos_directory():
    try:
        value = run(['xdg-user-dir', 'VIDEOS'])
        if value and Path(value).is_absolute(): return Path(value)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        pass
    return Path.home()/'Videos'


def monitor_at(monitors, cursor):
    """Hyprland coordinates are logical; output modes are physical and unrotated."""
    px, py = float(cursor['x']), float(cursor['y'])
    if not all(math.isfinite(v) for v in (px, py)): raise ValueError('Invalid pointer position.')
    for monitor in monitors:
        if monitor.get('disabled') or not monitor.get('name'): continue
        scale = float(monitor.get('scale', 1))
        if not math.isfinite(scale) or scale <= 0: continue
        width, height = monitor['width'], monitor['height']
        if int(monitor.get('transform', 0)) % 2: width, height = height, width
        x, y = monitor['x'], monitor['y']
        if x <= px < x+width/scale and y <= py < y+height/scale:
            return monitor['name']
    raise RuntimeError('The pointer is not on an active display.')


def pointer_monitor():
    cursor = json.loads(run(['hyprctl', '-j', 'cursorpos']))
    monitors = json.loads(run(['hyprctl', '-j', 'monitors']))
    return monitor_at(monitors, cursor)


def audio_source(mode):
    if mode == 'off': return None
    sources = json.loads(run(['pactl', '-f', 'json', 'list', 'sources']))
    if mode == 'desktop':
        sink = run(['pactl', 'get-default-sink'])
        source = next((s['name'] for s in sources
                       if s.get('monitor_of_sink_name') == sink or s['name'] == sink+'.monitor'), None)
    else:
        default = run(['pactl', 'get-default-source'])
        source = next((s['name'] for s in sources if s['name'] == default), None)
    if not source:
        raise RuntimeError('The selected audio source is unavailable. Choose another audio mode in Fusion Settings → Capture.')
    return source


def encoders():
    return set(re.findall(r'^\s*[VA][A-Z.]{5}\s+(\S+)', run(['ffmpeg', '-hide_banner', '-encoders']), re.M))


def software_encoder(available):
    for name in ('libx264', 'libopenh264', 'mpeg4'):
        if name in available: return name
    raise RuntimeError('No MP4 video encoder is available in FFmpeg.')


def choose_encoder(settings, available, transform=0):
    if settings['encoder'] == 'auto':
        candidates = []
        if 'h264_nvenc' in available: candidates.append(('h264_nvenc', None))
        # wf-recorder applies output rotation after the user filter; its CPU
        # transpose cannot follow a VA-API upload. Use a CPU-input encoder then.
        if 'h264_vaapi' in available and not transform:
            candidates.extend(('h264_vaapi', str(p)) for p in sorted(Path('/dev/dri').glob('renderD*')))
        for codec, device in candidates:
            command = ['ffmpeg', '-v', 'error', '-nostdin']
            if device: command += ['-vaapi_device', device]
            command += ['-f', 'lavfi', '-i', 'color=size=640x360:rate=64', '-frames:v', '1']
            if device: command += ['-vf', 'format=nv12,hwupload']
            command += ['-c:v', codec, '-f', 'null', '-']
            try:
                run(command, timeout=4)
                return codec, device
            except (OSError, RuntimeError, subprocess.SubprocessError): pass
    return software_encoder(available), None


def capture_command(settings, monitor, path, source, codec, device=None):
    # -r fixes the encoded frame rate; -D also captures a stationary desktop.
    command = ['wf-recorder', '--overwrite', '--output', monitor, '--framerate', str(settings['fps']),
               '--no-damage', '--muxer', 'nut', '--file', str(path), '--codec', codec, '--bframes', '0']
    # YUV 4:2:0 needs even dimensions, including odd-size nested/scaled outputs.
    video_filter = 'pad=ceil(iw/2)*2:ceil(ih/2)*2'
    quality = {'high': 20, 'balanced': 23, 'small': 28}[settings['quality']]
    if codec == 'libx264':
        command += ['--pixel-format', 'yuv420p', '-p', 'preset=veryfast', '-p', f'crf={quality}',
                    '-p', 'threads='+str(min(8, os.cpu_count() or 2))]
    elif codec == 'h264_nvenc':
        command += ['--pixel-format', 'yuv420p', '-p', 'preset=p4', '-p', f'cq={quality}']
    elif codec == 'h264_vaapi':
        command += ['--device', device, '--pixel-format', 'vaapi', '-p', f'qp={quality}']
        video_filter = 'scale_vaapi=w=ceil(iw/2)*2:h=ceil(ih/2)*2:format=nv12'
    else:
        bitrate = {'high': 20000000, 'balanced': 12000000, 'small': 6000000}[settings['quality']]
        command += ['--pixel-format', 'yuv420p', '-p', f'b={bitrate}']
    command += ['--filter', video_filter]
    if source:
        command += ['--audio='+source, '--audio-codec', 'aac', '-R', '48000', '-P', 'b=192000']
    return command


def media_streams(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(path)], timeout=15))['streams']


def notify(title, message, path=None):
    if path is not None:
        try:
            # The session-owned broker listens for actions after the banner
            # expires, without blocking capture or the next recording.
            subprocess.Popen([sys.executable, str(ROOT.parent/'scripts/screenshot-notify.py'),
                str(path), title, '--recording', '--body', message],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
            return
        except (OSError, subprocess.SubprocessError): pass
    try:
        subprocess.run(['notify-send', '-a', 'Hyper Fusion Recorder', '-i', 'media-record', title, message],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
    except (OSError, subprocess.SubprocessError): pass


class Recorder:
    """Own exact child handles; never signal a PID loaded from a state file."""
    def __init__(self, notify_fn=notify):
        self.notify = notify_fn
        self.state = {'phase': 'idle'}
        self.child = self.mux = self.log = None
        self.workspace = None
        self.deadline = 0
        self.reason = ''

    @property
    def busy(self): return self.state['phase'] in ('starting', 'recording', 'stopping', 'saving')

    def start(self, monitor, settings):
        if self.busy: raise RuntimeError('The previous recording is still being saved.')
        settings = validate(settings)
        for command in ('wf-recorder', 'ffmpeg', 'ffprobe'):
            if not shutil.which(command): raise RuntimeError('Install '+command+' through Hyper Fusion Setup to record your screen.')
        active = json.loads(run(['hyprctl', '-j', 'monitors']))
        if monitor not in [m['name'] for m in active if not m.get('disabled')]:
            raise RuntimeError('The selected display disconnected before recording started.')
        source = audio_source(settings['audio'])
        available = encoders()
        if source and 'aac' not in available: raise RuntimeError('The AAC audio encoder is unavailable.')
        output = next(m for m in active if m['name'] == monitor)
        codec, device = choose_encoder(settings, available, output.get('transform', 0))
        directory = Path(settings['directory']).expanduser() if settings['directory'] else videos_directory()
        directory.mkdir(parents=True, exist_ok=True)
        self.workspace = Path(tempfile.mkdtemp(prefix='.fusion-recording-', dir=directory))
        # Keep a recoverable stream while recording; publish MP4 after stopping.
        self.capture = self.workspace/'capture.nut'
        self.movie = self.workspace/'recording.mp4'
        self.destination = directory/recording_name(settings['filename'], monitor)
        self.log = (self.workspace/'capture.log').open('wb')
        self.settings, self.source, self.available = settings, source, available
        self.fallback = codec.startswith('h264_')
        self.reason = ''
        self.state = dict(phase='starting', monitor=monitor, fps=settings['fps'], audio=settings['audio'],
                          codec=codec, started=time.time(), file=str(self.destination))
        try:
            self.spawn(codec, device)
        except Exception:
            self.close_log(); shutil.rmtree(self.workspace); self.state = {'phase': 'idle'}
            raise

    def spawn(self, codec, device=None):
        self.state['codec'] = codec
        self.log_start = (self.workspace/'capture.log').stat().st_size
        self.child = subprocess.Popen(capture_command(self.settings, self.state['monitor'], self.capture,
            self.source, codec, device), stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log)
        self.deadline = time.monotonic()+12

    def receiving(self):
        if not self.capture.exists(): return False
        if self.capture.stat().st_size > 256: return True
        # A static screen may sit in the muxer's buffer for several seconds.
        # The format header is logged only after a frame and both codecs exist.
        with (self.workspace/'capture.log').open('rb') as stream:
            stream.seek(self.log_start)
            return b'Output #0,' in stream.read(65536)

    def stop(self, reason=''):
        if self.state['phase'] not in ('starting', 'recording'): return
        self.reason = reason
        if self.child and self.child.poll() is None: self.child.send_signal(signal.SIGINT)
        self.state['phase'] = 'stopping'
        self.deadline = time.monotonic()+15

    def tick(self):
        phase = self.state['phase']
        if phase in ('starting', 'recording', 'stopping'):
            code = self.child.poll()
            if code is not None:
                if phase == 'starting' and self.fallback:
                    self.fallback = False
                    self.capture.unlink(missing_ok=True)
                    self.spawn(software_encoder(self.available))
                    return
                if phase in ('starting', 'recording') and code != 0:
                    self.reason = 'Capture stopped unexpectedly.'
                self.begin_save()
            elif phase == 'starting':
                if self.receiving():
                    self.state['phase'] = 'recording'
                    self.notify('Recording '+self.state['monitor'], 'Alt + F9 stops and saves · '+self.settings['audio']+' audio')
                elif time.monotonic() > self.deadline:
                    self.stop('The recorder did not receive video frames.')
            elif phase == 'stopping' and time.monotonic() > self.deadline:
                self.child.kill(); self.child.wait()
                self.reason = 'The recorder did not stop cleanly.'
                self.begin_save()
        elif phase == 'saving' and self.mux.poll() is not None:
            if self.mux.returncode:
                self.fail('MP4 could not be saved. The captured video is retained for recovery.')
                return
            try:
                streams = media_streams(self.movie)
                if not any(s['codec_type'] == 'video' for s in streams): raise RuntimeError('The recording contains no video.')
                if self.source and not any(s['codec_type'] == 'audio' for s in streams):
                    raise RuntimeError('The selected audio source produced no audio stream.')
                # Atomic publication without replacing any existing recording.
                self.destination = publish_movie(self.movie, self.destination)
                self.state['file'] = str(self.destination)
                self.close_log(); shutil.rmtree(self.workspace)
                self.state = {**self.state, 'phase': 'saved', 'message': self.reason}
                self.notify('Recording saved', (self.reason+'\n' if self.reason else '')+str(self.destination), self.destination)
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
                self.fail(str(error))

    def begin_save(self):
        if not self.capture.exists() or self.capture.stat().st_size < 256:
            self.fail(self.reason or 'No video was received. Try a longer recording or software encoding.')
            return
        self.state['phase'] = 'saving'
        fps = self.state['fps']
        # wf-recorder's fps filter produces CFR frames, but some muxers infer
        # packet durations at a different rate. Normalize their timestamps at
        # copy time, retaining the first-frame offset and the untouched audio.
        # Capture explicitly disables B-frames, so packet and display order agree.
        timing = f'setts=pts=STARTPTS+N/({fps}*TB):dts=STARTDTS+N/({fps}*TB):duration=1/({fps}*TB)'
        self.mux = subprocess.Popen(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-i', str(self.capture),
            '-map', '0:v:0', '-map', '0:a:0?', '-c', 'copy', '-r', str(fps), '-bsf:v', timing,
            '-video_track_timescale', str(fps*1000), '-movflags', '+faststart', str(self.movie)],
            stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log)

    def close_log(self):
        if self.log: self.log.close(); self.log = None

    def fail(self, message):
        self.close_log()
        recovery = str(self.workspace) if self.workspace else ''
        self.state = {**self.state, 'phase': 'error', 'error': message, 'recovery': recovery}
        self.notify('Recording needs attention', message+('\nCapture and details: '+recovery if recovery else ''))

    def abort(self, message):
        for child in (self.child, self.mux):
            if child and child.poll() is None:
                child.kill(); child.wait()
        self.fail(message)

    def shutdown(self):
        self.stop('Recording ended with the desktop session.')
        until = time.monotonic()+45
        while self.busy and time.monotonic() < until:
            try: self.tick()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                self.abort(str(error))
            time.sleep(.1)
        for child in (self.child, self.mux):
            if child and child.poll() is None:
                child.kill(); child.wait()
        if self.busy: self.fail('Recording cleanup timed out. The captured video is retained for recovery.')
        self.close_log()
