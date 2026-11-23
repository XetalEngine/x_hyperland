"""Private, atomic preferences and bounded commands for desktop integrations."""
from pathlib import Path
import json
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get('XDG_STATE_HOME', str(Path.home()/'.local/state')))/'hyperfusion'


def run(argv, timeout=15, **kwargs):
    result = subprocess.run([str(a) for a in argv], text=True, capture_output=True, timeout=timeout, **kwargs)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or f'{Path(str(argv[0])).name} failed').strip()[-2000:])
    return result.stdout.strip()


def read(path, default):
    if not path.exists(): return dict(default)
    value = json.loads(path.read_text())
    if not isinstance(value, dict): raise ValueError(f'Invalid settings: {path.name}')
    return {**default, **value}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(json.dumps(value, indent=2)+'\n' if isinstance(value, dict) else value)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def install_packages(packages):
    """Only callers' fixed package lists are accepted; no shell or refresh-only upgrade."""
    allowed = {'wayvnc', 'kdeconnect', 'mpv', 'mpvpaper', 'hypridle', 'ddcutil'}
    if not packages or any(p not in allowed for p in packages): raise ValueError('Unknown desktop component.')
    if not Path('/usr/bin/pacman').exists():
        raise RuntimeError('Install these packages using your distribution’s software manager: '+', '.join(packages))
    return run(['/usr/bin/pkexec', '--disable-internal-agent', '/usr/bin/pacman', '-S', '--needed', '--noconfirm', *packages], timeout=900)


def monitors():
    value = json.loads(run(['hyprctl', '-j', 'monitors']))
    return [m for m in value if not m.get('disabled', False)]


def process_start(pid):
    try: return Path(f'/proc/{int(pid)}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, ValueError, IndexError): return ''
