"""Install the small shell-independent diagnostic command during foreground Setup."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'config/hypr/bin/fusion-check'
DESTINATION = Path('/usr/local/bin/fusion-check')
MARKER = b'# Hyper Fusion managed command: fusion-check v1\n'


def current(destination=DESTINATION):
    try:
        return (not destination.is_symlink() and destination.read_bytes() == SOURCE.read_bytes()
                and destination.stat().st_mode & 0o777 == 0o755)
    except OSError: return False


def write(destination=DESTINATION):
    """Atomic install; never overwrite an unrelated command or symlink."""
    content = SOURCE.read_bytes()
    if MARKER not in content: raise RuntimeError('Invalid Fusion diagnostic command.')
    if destination.is_symlink(): raise RuntimeError(str(destination)+' is a symlink; the existing command was preserved.')
    if destination.exists() and MARKER not in destination.read_bytes():
        raise RuntimeError(str(destination)+' belongs to another program; the existing command was preserved.')
    if current(destination): return
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.fusion-check-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content); stream.flush(); os.fchmod(stream.fileno(), 0o755); os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally: Path(temporary).unlink(missing_ok=True)


def install():
    if current(): return
    import runtime_install
    print('Installing fusion-check for all terminal shells…', flush=True)
    prefix = runtime_install.administrator()
    result = subprocess.run([*prefix, '/usr/bin/python3', str(Path(__file__).resolve()), '--install'],
                            capture_output=True, text=True)
    output = result.stdout+result.stderr
    runtime_install.check_administrator_result(prefix, result.returncode, output)
    if result.returncode: raise RuntimeError('Could not install fusion-check:\n'+output.strip())


if __name__ == '__main__':
    try:
        if sys.argv[1:] != ['--install'] or os.geteuid() != 0:
            raise RuntimeError('The installer requests administrator access for this system command.')
        write()
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr); sys.exit(1)
