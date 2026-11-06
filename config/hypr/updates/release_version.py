"""The desktop release label; commit identities still govern update safety."""
from pathlib import Path
import re

SOURCE_PATH = 'config/hypr/VERSION'
PATTERN = r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-(?:alpha|beta|rc))?'


def parse(value):
    if not isinstance(value, str) or len(value) > 80:
        raise ValueError('Invalid Hyper Fusion release version.')
    value = value.strip()
    if not re.fullmatch(PATTERN, value):
        raise ValueError('Expected a release version such as 0.0.0.199-alpha.')
    return value


def read(root):
    try: return parse((Path(root)/'VERSION').read_text())
    except FileNotFoundError: return ''  # Releases before version numbering.


def label(version, commit=''):
    try: return parse(version)
    except ValueError: return commit[:8] if commit else 'Unregistered'
