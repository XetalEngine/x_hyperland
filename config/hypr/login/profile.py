"""Publish theme/avatar copies for the greeter without exposing private homes."""
import json
import os
from pathlib import Path
import pwd
import tempfile

PROFILES = Path('/var/lib/xetal-fusion-login/profiles')


def read(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError): return {}


def atomic(path, data):
    descriptor, temporary = tempfile.mkstemp(prefix='.fusion-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream: stream.write(data)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def publish(root, destination=None, account=None):
    account = account or pwd.getpwuid(os.getuid())
    destination = destination or PROFILES/str(account.pw_uid)
    # Only administrator setup creates this directory. Ordinary installations do nothing.
    if not destination.is_dir(): return False
    state = read(root/'theme/state.json')
    design = state.get('design', 'modern')
    mode = state.get('mode', 'dark')
    palettes = read(root/'theme/palettes.json')
    supported = {'raw', 'modern', 'breakpoint', 'binaryknife'} | {
        name for name, value in palettes.items() if isinstance(value,dict) and all(key in value for key in ('dark','light','contrast'))}
    data = {'design': design if isinstance(design,str) and design in supported else 'modern',
            'mode': mode if mode in ('dark', 'light', 'contrast') else 'dark'}
    choice = state.get('avatar', 'assets/account.gif')
    avatar = Path(choice).expanduser() if isinstance(choice, str) and choice != 'auto' else None
    if avatar and not avatar.is_absolute(): avatar = root/'theme'/avatar
    candidates = [avatar, Path(account.pw_dir)/'.face.icon', Path(account.pw_dir)/'.face',
                  Path('/var/lib/AccountsService/icons')/account.pw_name, root/'theme/assets/account.gif']
    wallpaper = next((Path(item['path']) for item in read(root/'wallpaper/selection.json').values()
                      if isinstance(item, dict) and isinstance(item.get('path'), str) and Path(item['path']).is_file()), None)
    if wallpaper is None:
        default = read(root/'wallpaper/default.json').get('image')
        if isinstance(default, str): wallpaper = root/'wallpaper'/default
    selected_avatar = next((p for p in candidates if p and p.is_file()), None)
    for key, source in (('avatar', selected_avatar), ('wallpaper', wallpaper)):
        if not source or not source.is_file() or source.stat().st_size > 20*1024*1024: continue
        suffix = source.suffix.lower()
        if suffix not in ('.gif', '.png', '.jpg', '.jpeg', '.webp'): suffix = '.png'
        if key == 'wallpaper' and suffix == '.gif': continue
        name = key+('.jpg' if suffix == '.jpeg' else suffix)
        atomic(destination/name, source.read_bytes())
        data[key] = name
    atomic(destination/'profile.json', (json.dumps(data, indent=2)+'\n').encode())
    # Copies are intentionally public account artwork, never passwords or keyrings.
    if os.getuid() == 0:
        for item in destination.iterdir():
            if item.is_file(): os.chown(item, account.pw_uid, account.pw_gid)
    return True


if __name__ == '__main__':
    import argparse
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path.home()/'.config/hypr')
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    try: publish(args.root, args.destination)
    except OSError as error: print('Fusion sign-in artwork: '+str(error), file=sys.stderr)
