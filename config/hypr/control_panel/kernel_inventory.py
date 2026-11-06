#!/usr/bin/env python3
"""Read-only kernel inventory and configured Arch repository catalogue."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile


def run(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30,
                                env=dict(os.environ, LC_ALL='C'))
        return result.stdout.strip() if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ''


def fields(text):
    result = {}
    key = None
    for line in text.splitlines():
        if line.startswith('%') and line.endswith('%'):
            key = line.strip('%'); result[key] = []
        elif line and key:
            result[key].append(line)
    return result


def value(record, name):
    return next(iter(record.get(name, [])), '')


def children(path, pattern):
    try:
        return list(path.glob(pattern))
    except OSError:
        return []


def database_path():
    return Path(run(['pacman-conf', 'DBPath']) or '/var/lib/pacman')


def local_packages(database):
    result = {}
    for desc in children(database / 'local', '*/desc'):
        data = fields(read(desc))
        name = value(data, 'NAME')
        if name:
            data['FILES'] = fields(read(desc.with_name('files'))).get('FILES', [])
            result[name] = data
    return result


def image_release(image):
    # file knows bzImage and compressed images. Unified kernel images expose
    # their release in .uname; objcopy's explicit output prevents input writes.
    if image.suffix.lower() == '.efi':
        result = run(['objcopy', '--dump-section', '.uname=/dev/stdout', str(image), '/dev/null']).strip('\0\n ')
        if re.fullmatch(r'[A-Za-z0-9_.+~-]+', result):
            return result
    result = run(['file', '-Lb', str(image)])
    match = re.search(r'\bversion ([^\s,]+)', result)
    return match[1] if match else ''


def inventory(root=Path('/'), running=None, database=None):
    running = running or platform.release()
    packages = local_packages(database or database_path())
    owners = {}
    for name, data in packages.items():
        for path in data.get('FILES', []):
            if re.search(r'(?:^|/)lib/modules/[^/]+/(?:vmlinuz|pkgbase)$', path) or path.startswith('boot/vmlinuz'):
                owners[path] = name
    records = {}
    def add(release, image='', package='', modules=False):
        key = release or image
        row = records.setdefault(key, dict(release=release, images=[], package='', version='',
                                           running=bool(release and release == running), installed=False, headers=False))
        if image and image not in row['images']:
            row['images'].append(image)
        row['installed'] |= bool(image or modules)
        if package in packages:
            row['package'] = package
            row['version'] = value(packages[package], 'VERSION')
            row['headers'] |= package + '-headers' in packages
        return row
    seen = set()
    for base in ('usr/lib/modules', 'lib/modules'):
        for directory in children(root / base, '*'):
            if not directory.is_dir() or directory.resolve() in seen:
                continue
            seen.add(directory.resolve())
            pkgbase = read(directory / 'pkgbase')
            image = directory / 'vmlinuz'
            modules = (directory / 'kernel').is_dir() or (directory / 'modules.dep').is_file()
            if not (pkgbase or image.is_file() or modules or directory.name == running):
                continue  # A headers-only directory is not an installed kernel.
            package = owners.get(str(image.relative_to(root)), '') or owners.get(str((directory / 'pkgbase').relative_to(root)), '') or pkgbase
            row = add(directory.name, '/' + str(image.relative_to(root)) if image.is_file() else '', package, modules or bool(pkgbase))
            row['headers'] |= (directory / 'build/Makefile').is_file()
    images = []
    for base, pattern in (('boot', 'vmlinuz*'), ('boot', 'kernel*'), ('boot/EFI/Linux', '*.efi'),
                          ('efi/EFI/Linux', '*.efi'), ('boot/efi/EFI/Linux', '*.efi')):
        images.extend(children(root / base, pattern))
    for image in images:
        if not image.is_file():
            continue
        path = str(image.relative_to(root))
        release = image_release(image)
        package = owners.get(path, '')
        # Arch install hooks copy /usr/lib/modules/<release>/vmlinuz to /boot.
        # When boot files cannot be read, pkgbase still identifies their owner.
        if not release:
            candidates = [r for r in records.values() if r['package'] and image.name == 'vmlinuz-' + r['package']]
            if len(candidates) == 1:
                release = candidates[0]['release']; package = candidates[0]['package']
        add(release, '/' + path, package)
    current = add(running)
    # uname is authoritative even after an upgrade removed the running image.
    current['running'] = True
    for row in records.values():
        row['image'] = ', '.join(row['images']) or ('Modules: ' + row['release'] if row['installed'] else 'Running kernel · boot files unavailable')
    return dict(running=running, kernels=sorted(records.values(), key=lambda r: (not r['running'], r['release'], r['image'])))


def is_kernel(data):
    name = value(data, 'NAME')
    description = value(data, 'DESC').lower()
    if value(data, 'BASE') and value(data, 'BASE') != name:
        return False  # Headers, drivers and debug files from a split kernel build.
    if re.search(r'(?:^|-)(?:headers|docs?|firmware|api|tools|utils|nvidia|zfs|virtualbox|dkms)(?:-|$)', name):
        return False
    return (bool(re.fullmatch(r'linux(?:[0-9]+|[-a-z0-9+.]+)?', name))
            and ('kernel' in description and ('modules' in description or 'linux' in description)))


def catalog(database=None, repositories=None):
    database = database or database_path()
    repositories = run(['pacman-conf', '--repo-list']).splitlines() if repositories is None else repositories
    installed = local_packages(database)
    rows = []
    missing = []
    for repo in repositories:
        if not re.fullmatch(r'[A-Za-z0-9_.+-]+', repo):
            continue
        try:
            with tarfile.open(database / 'sync' / (repo + '.db')) as archive:
                entries = {}
                for member in archive:
                    if member.isfile() and member.name.endswith('/desc') and member.size < 1024 * 1024:
                        data = fields(archive.extractfile(member).read().decode('utf-8', errors='replace'))
                        entries[value(data, 'NAME')] = data
        except (OSError, tarfile.TarError):
            missing.append(repo); continue
        for name, data in entries.items():
            if not is_kernel(data):
                continue
            headers = name + '-headers'
            rows.append(dict(package=name, repo=repo, version=value(data, 'VERSION'),
                             description=value(data, 'DESC'), installed=value(installed.get(name, {}), 'VERSION'),
                             headers=headers if headers in entries else '', method='pacman'))
    result = dict(kernels=rows, missing_repositories=missing)
    # This exact historical build is often absent from current repository DBs.
    # Offer the confirmed KVM installer separately from ordinary repo targets.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'kvm'))
    try:
        import kernel_install
        if not kernel_install.platform_problem():
            target = kernel_install.Target.parse(kernel_install.required_kernel())
            result['kvm_kernel'] = dict(release=target.release, installed=kernel_install.complete(target))
    except (OSError, ValueError, RuntimeError) as error:result['kvm_kernel_error'] = str(error)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inventory', 'catalog'))
    args = parser.parse_args()
    print(json.dumps(inventory() if args.action == 'inventory' else catalog()))


if __name__ == '__main__':
    main()
