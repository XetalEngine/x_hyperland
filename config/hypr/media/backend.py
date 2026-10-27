"""YouTube-only requests and yt-dlp commands, without shell interpretation."""
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
STATE = Path.home()/'.local/state/hyprland-media'
PRIVATE_TOOL = STATE/'bin/yt-dlp'
VIDEO_ID = re.compile(r'[A-Za-z0-9_-]{11}')
FORMATS = {'mp3': ('MUSIC', 'Music'), 'mp4': ('VIDEOS', 'Videos')}


def youtube_url(text):
    text = text.strip().strip('<>\"\'')
    if len(text) > 8192 or any(c in text for c in '\r\n\0'):
        raise ValueError('Paste one YouTube video address or video ID.')
    if VIDEO_ID.fullmatch(text):
        return 'https://www.youtube.com/watch?v='+text
    if re.match(r'(?i)(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)/', text):
        text = 'https://'+text
    try:
        url = urlsplit(text)
        if url.scheme not in ('http', 'https') or url.username or url.password or url.port not in (None, 80, 443):
            raise ValueError()
        host = (url.hostname or '').lower()
        parts = url.path.strip('/').split('/')
        ident = ''
        if host in ('youtu.be', 'www.youtu.be') and len(parts) == 1:
            ident = parts[0]
        elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'www.youtube-nocookie.com'):
            if parts == ['watch']:
                ident = parse_qs(url.query).get('v', [''])[0]
            elif len(parts) == 2 and parts[0] in ('shorts', 'live', 'embed', 'v'):
                ident = parts[1]
        if VIDEO_ID.fullmatch(ident):
            return 'https://www.youtube.com/watch?v='+ident
    except ValueError:
        pass
    raise ValueError('Enter a YouTube video link, Shorts link, or 11-character video ID.')


def selected_url(text):
    """Only prefill recognizable video links; never copy unrelated selected text."""
    if len(text) > 131072:
        return ''
    candidates = [text.strip(), *re.findall(r'https?://[^\s<>\"\']+', text)]
    for candidate in candidates:
        try:
            return youtube_url(candidate.rstrip('.,);]'))
        except ValueError:
            pass
    return ''


def prefill(text):
    return selected_url(text) or text.strip()[:8192]


def primary_selection():
    try:
        with subprocess.Popen(['wl-paste', '--primary', '--no-newline', '--type', 'text'],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
            try:
                output, _ = process.communicate(timeout=0.8)
            except subprocess.TimeoutExpired:
                process.kill(); process.communicate(); return ''
        return prefill(output.decode('utf-8', 'replace')) if process.returncode == 0 else ''
    except OSError:
        return ''


def destination(kind, runner=subprocess.run):
    key, fallback = FORMATS[kind]
    try:
        result = runner(['xdg-user-dir', key], capture_output=True, text=True, timeout=2)
        value = Path(result.stdout.strip())
        if result.returncode == 0 and value.is_absolute() and value != Path.home():
            return value
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.home()/fallback


def tool(private=PRIVATE_TOOL):
    if private.is_file():
        return [sys.executable, str(private)]
    installed = shutil.which('yt-dlp')
    if not installed:
        raise ValueError('yt-dlp is missing. Use Update yt-dlp to install it for this popup.')
    return [installed]


def version(argv=None):
    result = subprocess.run([*(argv or tool()), '--ignore-config', '--version'],
                            capture_output=True, text=True, timeout=12)
    value = result.stdout.strip()
    if result.returncode or not re.fullmatch(r'\d{4}\.\d{2}\.\d{2}(?:[.\w+-]*)', value):
        raise ValueError('Could not read the yt-dlp version. Use Update yt-dlp to repair it.')
    return value


def command(url, kind, folder, executable=None):
    if kind not in FORMATS:
        raise ValueError('Choose MP3 or MP4.')
    url = youtube_url(url)
    missing = [name for name in ('ffmpeg', 'ffprobe') if not shutil.which(name)]
    if missing:
        raise ValueError('Install FFmpeg to download MP3 or merge high-quality MP4 video.')
    runtime = next((name for name in ('deno', 'node', 'qjs') if shutil.which(name)), None)
    if not runtime:
        raise ValueError('Install Deno or Node.js for YouTube downloads.')
    args = [*(executable or tool()), '--ignore-config', '--no-playlist', '--no-simulate',
            '--newline', '--no-color', '--no-quiet', '--progress', '--progress-delta', '0.3',
            '--socket-timeout', '15', '--retries', '3', '--fragment-retries', '3',
            '--no-overwrites', '--no-post-overwrites', '--embed-metadata',
            '--js-runtimes', 'quickjs' if runtime == 'qjs' else runtime,
            '--paths', str(folder), '--output', '%(title).160B [%(id)s].%(ext)s',
            '--progress-template', 'download:__XETAL_PROGRESS__%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s',
            '--print', 'before_dl:__XETAL_TITLE__%(title)j',
            '--print', 'after_move:__XETAL_FILE__%(filepath)j']
    if kind == 'mp3':
        args += ['--format', 'bestaudio/best', '--extract-audio', '--audio-format', 'mp3', '--audio-quality', '0']
    else:
        args += ['--format', 'bestvideo+bestaudio/best', '--merge-output-format', 'mp4', '--remux-video', 'mp4']
    return args+['--', url]


def output_event(line):
    line = line.strip()
    for prefix, kind in [('__XETAL_TITLE__', 'title'), ('__XETAL_FILE__', 'file')]:
        if line.startswith(prefix):
            try:
                value = json.loads(line[len(prefix):])
                if isinstance(value, str):
                    return {'type': kind, 'text': value}
            except ValueError:
                pass
    if line.startswith('__XETAL_PROGRESS__'):
        parts = line[len('__XETAL_PROGRESS__'):].split('|')
        match = re.search(r'(\d+(?:\.\d+)?)%', parts[0])
        return {'type': 'progress', 'percent': min(100, float(match[1])) if match else None,
                'text': '  ·  '.join(part.strip() for part in parts if part.strip() not in ('NA', 'Unknown'))}
    return {'type': 'log', 'text': line[:16384]}


def download(url, kind, emit, folder=None, executable=None):
    folder = Path(folder) if folder else destination(kind)
    args = command(url, kind, folder, executable)
    folder.mkdir(parents=True, exist_ok=True)
    emit({'type': 'log', 'text': 'Saving '+kind.upper()+' to '+str(folder)})
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          stdin=subprocess.DEVNULL, text=True, errors='replace', bufsize=1) as process:
        final = None
        for line in process.stdout:
            event = output_event(line)
            if event['type'] == 'file':
                final = Path(event['text'])
            emit(event)
        code = process.wait()
    if code:
        raise ValueError('Download failed. The log above contains the yt-dlp error; try Update yt-dlp if YouTube changed.')
    if final is None or not final.is_file() or final.suffix.lower() != '.'+kind:
        raise ValueError('No completed '+kind.upper()+' file was produced. Check the download log.')
    emit({'type': 'success', 'text': 'Saved '+final.name, 'file': str(final)})
