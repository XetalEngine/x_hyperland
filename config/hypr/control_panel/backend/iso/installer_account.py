"""Account choices for Hyper Fusion's restore wizard; apply only in the mounted target."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import tempfile

NAME = re.compile(r'[a-z_][a-z0-9_-]{0,31}\Z')
HASH = re.compile(r'\$6\$[a-zA-Z0-9./]{1,16}\$[a-zA-Z0-9./]{86}\Z')


def password_hash(password):
    """Use the system password encoder without a strength policy or CLI truncation."""
    if '\x00' in password:
        raise ValueError('Password: a NUL character cannot be used in a login password.')
    for soname in ('libcrypt.so.2', 'libcrypt.so.1'):
        try:
            library = ctypes.CDLL(soname, use_errno=True)
            break
        except OSError: continue
    else: raise ValueError('The live installer is missing its system password encoder.')
    # crypt_rn uses a caller-owned buffer, so no static password data is shared.
    library.crypt_rn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int]
    library.crypt_rn.restype = ctypes.c_char_p
    buffer = ctypes.create_string_buffer(32768)  # libxcrypt's public crypt_data size.
    salt = '$6$'+''.join(secrets.choice('./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz') for _ in range(16))
    result = library.crypt_rn(password.encode('utf-8'), salt.encode('ascii'), buffer, len(buffer))
    encoded = result.decode('ascii') if result else ''
    ctypes.memset(buffer, 0, len(buffer))
    if not HASH.fullmatch(encoded):
        raise ValueError('Password: the system password encoder could not accept this value.')
    return encoded


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
    name = name.strip().lower()
    if not NAME.fullmatch(name):
        raise ValueError('Username: use 1–32 letters, numbers, underscores or dashes; start with a letter or underscore. Capitals become lowercase.')
    if not users or not 0 <= index < len(users):
        raise ValueError('This snapshot has no regular account whose desktop can be transferred.')
    user = users[index]
    if name == user['name']:
        raise ValueError('Choose a new username for this installation.')
    if name != user['name'] and name in reserved:
        raise ValueError('Username: that name is already used by an account, group or home folder.')
    if any(u['name'] == name and u['uid'] != user['uid'] for u in users):
        raise ValueError('That username already belongs to another account.')
    if password != confirmation: raise ValueError('The passwords do not match.')
    if not password: raise ValueError('Enter a password for the new account. Any length or strength is allowed.')
    # Only the encrypted hash ever leaves this process.
    encoded = password_hash(password)
    return dict(change=True, original=user['name'],
                uid=user['uid'], username=name, password_hash=encoded)


def require_fresh(plan):
    """Enforce the build's fresh-account contract before formatting or applying."""
    if not isinstance(plan, dict) or plan.get('change') is not True:
        raise ValueError('This ISO requires a new administrator username and password.')
    if set(plan) != {'change', 'original', 'uid', 'username', 'password_hash'}:
        raise ValueError('Invalid account choice fields.')
    old, new, encoded = plan['original'], plan['username'], plan['password_hash']
    if not all(isinstance(n, str) and NAME.fullmatch(n) for n in (old, new)):
        raise ValueError('Invalid account name.')
    if old == new: raise ValueError('Choose a new username for this installation.')
    if not isinstance(encoded, str) or not HASH.fullmatch(encoded):
        raise ValueError('A password for the new account is required.')
    if type(plan['uid']) is not int or not 1000 <= plan['uid'] < 60000:
        raise ValueError('Invalid source account identifier.')
    return old, new, encoded


def validate(plan, target):
    if plan == {'change':False}: return None
    old, new, encoded = require_fresh(plan)
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
    memberships = [g[0] for g in groups if len(g) == 4 and old in g[3].split(',') and g[2] != user[3]]
    return old, new, home, new_home, bool(private), encoded, int(user[3]), user[6], memberships


def migrate_profile(target, old_home, new_home):
    """Repair this desktop's installed absolute paths after transferring home."""
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


def check_sudo_policy(target, run):
    """Repair only permission mismatches reported by the target's own validator."""
    report = run('visudo', '--check', check=False)
    if report.returncode == 0: return
    # Let visudo discover includes (including explicit .conf files), rather than
    # guessing which files in sudoers.d are policy and which are ignored backups.
    mismatches = re.findall(r'^(/[^\r\n]+): bad permissions, should be mode (0[0-7]{3})$',
                            report.stderr or '', re.MULTILINE)
    descriptors, repairs, changed = [], [], []
    try:
        for relative, expected in dict.fromkeys(mismatches):
            mode = int(expected, 8)
            if mode not in (0o400, 0o440): continue
            path = confined(target, relative)
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            descriptors.append(descriptor)
            metadata = os.fstat(descriptor)
            original = stat.S_IMODE(metadata.st_mode)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0
                    or metadata.st_nlink != 1 or original & 0o7022):
                raise ValueError('Cannot repair an untrusted or linked restored sudo policy: '+relative)
            repairs.append((descriptor, original, mode, relative))
        for descriptor, original, mode, relative in repairs:
            os.fchmod(descriptor, mode); changed.append((descriptor, original))
        # Ownership, syntax and every included rule still have to pass. Any
        # unrelated error restores the original modes before account changes.
        run('visudo', '--check')
        for _, _, mode, relative in repairs:
            print('Restored sudo policy permissions corrected: '+relative+' ('+format(mode, '04o')+').')
    except Exception:
        for descriptor, original in reversed(changed): os.fchmod(descriptor, original)
        raise
    finally:
        for descriptor in descriptors: os.close(descriptor)


def ensure_administrator(target, username, uid, run):
    """Grant the chosen account sudo in the restored OS, including name-only policies."""
    sudoers = confined(target, 'etc/sudoers')
    directory = confined(target, 'etc/sudoers.d')
    # An explicit include also works when the source never enabled includedir.
    # The dot keeps includedir from loading our rule a second time. Keying the
    # file by preserved UID lets subsequent restores replace their own rule.
    relative = '/etc/sudoers.d/hyper-fusion-'+str(uid)+'.conf'
    policy = confined(target, relative)
    marker = '# Managed by the Hyper Fusion restore installer.\n'
    if sudoers.is_symlink() or directory.is_symlink() or policy.is_symlink():
        raise ValueError('The restored sudo policy must use regular files and directories.')
    original = sudoers.read_bytes()
    metadata = sudoers.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError('The restored sudoers file is not a regular file.')
    previous = policy.read_bytes() if policy.exists() else None
    if previous is not None and not previous.startswith(marker.encode()):
        raise ValueError('An existing sudo policy uses the installer’s reserved filename.')
    include = '@include '+relative
    updated = original
    if include.encode() not in original.splitlines():
        updated = original.rstrip(b'\n')+b'\n\n'+include.encode()+b'\n'
    directory.mkdir(mode=0o755, exist_ok=True)
    if directory.stat().st_uid != 0 or directory.stat().st_mode & 0o022:
        raise ValueError('The restored sudoers directory must be owned by root and not writable by other users.')

    def replace(path, data, mode, owner, group):
        descriptor, temporary = tempfile.mkstemp(prefix='.hyper-fusion-', dir=path.parent)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                os.fchown(stream.fileno(), owner, group)
                os.fchmod(stream.fileno(), mode)
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    # Keep the original policy intact if validation fails. No host sudo files
    # are touched, and no passwordless rule is created.
    try:
        contents = (marker+'Defaults:'+username+' !rootpw, !targetpw, !runaspw, runas_default=root\n'
                    +username+' ALL=(ALL:ALL) PASSWD: ALL\n')
        replace(policy, contents.encode(), 0o440, 0, 0)
        if updated != original:
            replace(sudoers, updated, stat.S_IMODE(metadata.st_mode), metadata.st_uid, metadata.st_gid)
        check_sudo_policy(target, run)  # Check the complete policy and all includes.
    except Exception:
        if updated != original:
            replace(sudoers, original, stat.S_IMODE(metadata.st_mode), metadata.st_uid, metadata.st_gid)
        if previous is None: policy.unlink(missing_ok=True)
        else: replace(policy, previous, 0o440, 0, 0)
        raise


def apply(plan, target):
    target = Path(target).resolve(strict=True)
    if target == Path('/') or not target.is_mount():
        raise ValueError('Account changes require the mounted restore target.')
    details = validate(plan, target)
    if details is None: return
    old, new, home, new_home, private, encoded, gid, shell, memberships = details
    def run(*args, input=None, check=True):
        result = subprocess.run(['arch-chroot', str(target), *args], input=input,
                                text=True, capture_output=True, env={**os.environ, 'LC_ALL':'C'})
        if result.returncode and check:
            # The account tools' errors help diagnose a failed rename. Never
            # include password-tool output or its encrypted input in a log.
            detail = result.stderr.strip() if args[0] != 'chpasswd' else ''
            message = 'Restored account update failed: '+args[0]+' (exit '+str(result.returncode)+').'
            if detail: message += ' '+detail[:1200]
            raise RuntimeError(message)
        return result
    check_sudo_policy(target, run)
    # Recreate the login and shadow entry instead of retaining the source
    # account's password/expiry state. Keep its numeric ownership so the cloned
    # desktop and files belong to the new user without a filesystem-wide chown.
    # Rename the private group first so userdel's optional same-name group
    # cleanup cannot remove it; other accounts may share that numeric group.
    if private: run('groupmod', '--new-name', new, old)
    run('userdel', old)
    source_home = confined(target, home)
    destination_home = confined(target, new_home)
    if home != new_home and source_home.exists():
        destination_home.parent.mkdir(parents=True, exist_ok=True)
        source_home.rename(destination_home)
    command = ['useradd', '--uid', str(plan['uid']), '--gid', str(gid), '--home-dir', new_home,
               '--shell', shell, '--comment', new, '--no-user-group',
               '--no-create-home' if destination_home.exists() else '--create-home']
    if memberships: command += ['--groups', ','.join(memberships)]
    run(*command, new)
    run('chpasswd', '--encrypted', input=new+':'+encoded+'\n')
    migrate_profile(target, home, new_home)
    migrate_autologin(target, old, new)
    ensure_administrator(target, new, plan['uid'], run)
    print('New administrator account created in the restored system.')


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
