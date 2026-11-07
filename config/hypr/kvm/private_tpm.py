"""Keep private emulated TPM state readable by the guest's desktop owner."""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import pwd
import re
import stat


STATE_FILE = re.compile(r'(?:tpm[12]-[0-9a-fA-F]{2}\.(?:permall|volatilestate|savestate)|\.lock)\Z')


@contextmanager
def directory(path, root, uid):
    """Anchor operations to owned directories; never follow guest symlinks."""
    path, root = Path(path).absolute(), Path(root).absolute()
    parts = path.relative_to(root).parts
    if not parts or '..' in parts or root.resolve() != root:
        raise ValueError('Select a private TPM directory inside the KVM workspace.')
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if os.fstat(fd).st_uid != uid:
            raise ValueError('The KVM workspace must belong to the desktop user.')
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
            if os.fstat(fd).st_uid not in (0, uid):
                raise ValueError('The TPM directory belongs to another user.')
        yield fd
    finally:
        os.close(fd)


def owner(uid, gid):
    if uid <= 0 or pwd.getpwuid(uid).pw_gid != gid:
        raise ValueError('Use the desktop account and its primary group for private TPM state.')


def own_file(fd, uid, gid):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid not in (0, uid):
        raise ValueError('TPM files must be ordinary private files, without links or another owner.')
    if os.geteuid() == 0:
        os.fchown(fd, uid, gid)
    os.fchmod(fd, 0o600)


def repair(state, root, uid, gid):
    """Restore ownership only; never create, replace, or regenerate guest keys."""
    owner(uid, gid)
    with directory(state, root, uid) as fd:
        names = [name for name in os.listdir(fd) if STATE_FILE.fullmatch(name)]
        if not any(name.endswith('.permall') for name in names):
            raise ValueError('Existing TPM state was not found. No keys were created.')
        # Validate every file before changing any permissions.
        opened = []
        try:
            for name in names:
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                opened.append(child)
                info = os.fstat(child)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid not in (0, uid):
                    raise ValueError('TPM state contains a link or a file owned by another user.')
            for child in opened:
                own_file(child, uid, gid)
            if os.geteuid() == 0:
                os.fchown(fd, uid, gid)
            os.fchmod(fd, 0o700)
        finally:
            for child in opened: os.close(child)


def process_options(state, uid, gid, root=None):
    from portable import data_root
    root = Path(root) if root is not None else data_root()
    # External/libvirt-owned state retains its existing launch policy.
    if not Path(state).absolute().is_relative_to(root.absolute()):
        return {}
    repair(state, root, uid, gid)
    return {'user': uid, 'group': gid, 'extra_groups': []} if os.geteuid() == 0 else {}


def runtime_files(path, root, uid, gid):
    """Upgrade only the two files used by the generated Single GPU hook."""
    with directory(path, root, uid) as fd:
        for name in ('swtpm.pid', 'swtpm.log'):
            child = os.open(name, os.O_RDONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                            0o600, dir_fd=fd)
            try: own_file(child, uid, gid)
            finally: os.close(child)
        if os.geteuid() == 0: os.fchown(fd, uid, gid)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repair', action='store_true')
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--uid', type=int, required=True)
    parser.add_argument('--gid', type=int, required=True)
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.repair:
        repair(args.state, args.root, args.uid, args.gid)
        print('Existing TPM state permissions restored. Guest keys were preserved.')
        return
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command: parser.error('A TPM command is required.')
    options = process_options(args.state, args.uid, args.gid, args.root)
    if options:
        if args.run_dir: runtime_files(args.run_dir, args.root, args.uid, args.gid)
        os.setgroups([]); os.setgid(args.gid); os.setuid(args.uid)
        os.environ['HOME'] = pwd.getpwuid(args.uid).pw_dir
    os.execvp(command[0], command)


if __name__ == '__main__':
    main()
