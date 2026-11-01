"""Account choices for Hyper Fusion's restore wizard; apply only in the mounted target."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

NAME = re.compile(r'[a-z_][a-z0-9_-]{0,31}\Z')
HASH = re.compile(r'\$6\$[a-zA-Z0-9./]{1,16}\$[a-zA-Z0-9./]{86}\Z')


def confined(target, relative):
    path = target / relative.lstrip('/')
    if not path.resolve().is_relative_to(target.resolve()):
        raise ValueError('A restored account path points outside the installation target.')
    return path


def accounts(path):
    result = []
    for line in Path(path).read_text().splitlines():
        fields = line.split('\t')
        if len(fields) != 4: continue
        name, uid, gid, home = fields
        if not NAME.fullmatch(name) or not uid.isdecimal() or not gid.isdecimal(): continue
        if not 1000 <= int(uid) < 60000 or name == 'nobody': continue
        if not home.startswith('/') or any(ord(c) < 32 for c in home): continue
        result.append(dict(name=name, uid=int(uid), gid=int(gid), home=home))
    return result


def choice(users, index, name, password, confirmation, reserved=()):
    if not NAME.fullmatch(name):
        raise ValueError('Use 1–32 lowercase letters, numbers, underscores or dashes; start with a letter or underscore.')
    user = users[index]
    if name != user['name'] and name in reserved:
        raise ValueError('That name is already used by an account, group or home folder.')
    if any(u['name'] == name and u['uid'] != user['uid'] for u in users):
        raise ValueError('That username already belongs to another account.')
    if password != confirmation: raise ValueError('The passwords do not match.')
    if any(c in password for c in '\n\r\x00') or len(password.encode()) > 512:
        raise ValueError('Choose a password without line breaks, up to 512 bytes.')
    encoded = ''
    if password:
        # Passwords never appear in argv, environment, temporary files or logs.
        result = subprocess.run(['openssl', 'passwd', '-6', '-stdin'], input=password+'\n',
                                text=True, capture_output=True, timeout=10)
        encoded = result.stdout.strip()
        if result.returncode or not HASH.fullmatch(encoded):
            raise ValueError('Could not prepare the password. Try again or keep the existing password.')
    return dict(change=name != user['name'] or bool(encoded), original=user['name'],
                uid=user['uid'], username=name, password_hash=encoded)


def validate(plan, target):
    if not isinstance(plan, dict) or type(plan.get('change')) is not bool:
        raise ValueError('Invalid account choice.')
    if not plan['change']: return None
    if set(plan) != {'change', 'original', 'uid', 'username', 'password_hash'}:
        raise ValueError('Invalid account choice fields.')
    old, new, encoded = plan['original'], plan['username'], plan['password_hash']
    if not all(isinstance(n, str) and NAME.fullmatch(n) for n in (old, new)):
        raise ValueError('Invalid account name.')
    if not isinstance(encoded, str) or (encoded and not HASH.fullmatch(encoded)):
        raise ValueError('Invalid password hash.')
    records = [line.split(':') for line in confined(target,'etc/passwd').read_text().splitlines()]
    user = next((u for u in records if len(u) == 7 and u[0] == old), None)
    if not user or type(plan['uid']) is not int or not 1000 <= plan['uid'] < 60000 or int(user[2]) != plan['uid']:
        raise ValueError('The selected account does not match the restored snapshot.')
    if old != new and any(u[0] == new for u in records): raise ValueError('The new account name is already in use.')
    home = user[5]
    if not home.startswith('/'): raise ValueError('The restored home path is invalid.')
    confined(target,home)
    new_home = '/home/'+new if home == '/home/'+old else home
    if new_home != home and os.path.lexists(confined(target,new_home)):
        raise ValueError('The new home folder already exists; choose another username.')
    groups = [line.split(':') for line in confined(target,'etc/group').read_text().splitlines()]
    private = next((g for g in groups if len(g) == 4 and g[0] == old and g[2] == user[3]), None)
    if private and old != new and any(g[0] == new for g in groups):
        raise ValueError('A group with the new username already exists.')
    return old, new, home, new_home, bool(private), encoded


def migrate_profile(target, old_home, new_home):
    """Repair this desktop's installed absolute paths after usermod moves home."""
    if old_home == new_home: return
    profile = confined(target,new_home+'/.config/hypr')
    if not profile.is_dir() or profile.is_symlink(): return
    ignored = {'.build', 'build', 'cache', 'state', '__pycache__', '.git', 'data', 'font-cache'}
    for directory, folders, files in os.walk(profile, followlinks=False):
        folders[:] = [f for f in folders if f not in ignored and not (Path(directory)/f).is_symlink()]
        for name in files:
            path = Path(directory)/name
            if path.is_symlink() or path.stat().st_size > 4_000_000: continue
            data = path.read_bytes()
            if b'\0' in data: continue
            try: text = data.decode('utf-8')
            except UnicodeError: continue
            # Do not turn /home/alice-other into /home/bob-other.
            changed = re.sub(re.escape(old_home)+r'(?=/|[\s"\'\\]|$)', lambda _: new_home, text)
            if text != changed:
                if name == '.xetal-update.json':
                    inventory = json.loads(changed)
                    for entry in inventory.get('files',{}).values():
                        if 'text' in entry:
                            entry['sha256'] = hashlib.sha256(entry['text'].encode()).hexdigest()
                    changed = json.dumps(inventory,indent=2)+'\n'
                path.write_text(changed)


def migrate_autologin(target, old, new):
    if old == new: return
    candidates = [target/'etc/sddm.conf', target/'etc/lightdm/lightdm.conf',
                  target/'etc/gdm/custom.conf']
    candidates += list((target/'etc/sddm.conf.d').glob('*.conf'))
    candidates += list((target/'etc/lightdm/lightdm.conf.d').glob('*.conf'))
    for path in candidates:
        if not path.is_file() or path.is_symlink(): continue
        confined(target,str(path.relative_to(target)))
        text = path.read_text()
        keys = r'(?:User|autologin-user|AutomaticLogin)'
        updated = re.sub(r'(?m)^(\s*'+keys+r'\s*=\s*)'+re.escape(old)+r'(\s*)$',
                         lambda m: m[1]+new+m[2], text)
        if updated != text: path.write_text(updated)


def apply(plan, target):
    target = Path(target).resolve(strict=True)
    if target == Path('/') or not target.is_mount():
        raise ValueError('Account changes require the mounted restore target.')
    details = validate(plan, target)
    if details is None: return
    old, new, home, new_home, private, encoded = details
    def run(*args, input=None):
        result = subprocess.run(['arch-chroot', str(target), *args], input=input,
                                text=True, capture_output=True)
        # Do not include subprocess output in exceptions: chpasswd input is private.
        if result.returncode: raise RuntimeError('Could not finish the restored account update ('+args[0]+').')
    if old != new:
        command = ['usermod', '--login', new]
        if new_home != home: command += ['--home', new_home, '--move-home']
        run(*command, old)
        if private: run('groupmod', '--new-name', new, old)
        migrate_profile(target, home, new_home)
        migrate_autologin(target, old, new)
    if encoded: run('chpasswd', '--encrypted', input=new+':'+encoded+'\n')
    print('Account preferences applied to the restored system.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    try:
        if os.geteuid() != 0: raise ValueError('Run account setup from the live installer.')
        raw = sys.stdin.read(8193)
        if len(raw) > 8192: raise ValueError('Account choice is too large.')
        apply(json.loads(raw), args.target)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr); return 1
    return 0


if __name__ == '__main__': raise SystemExit(main())
