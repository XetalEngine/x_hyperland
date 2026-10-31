#!/usr/bin/env python3
"""Unpack verified corresponding sources; optionally build in a disposable Debian 13 system.

This helper never installs packages, edits repositories or invokes sudo.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent


def prepare(destination):
    manifest = json.loads((ROOT.parents[2]/'config/hypr/runtime/debian-13.json').read_text())
    for item in manifest['sources']:
        path = ROOT/item['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise RuntimeError('Source checksum mismatch: '+path.name)
    destination.mkdir(parents=True, exist_ok=False)
    inputs = json.loads((ROOT/'sources/build-inputs.json').read_text())
    for item in inputs:
        output = destination/item['directory']
        with tempfile.TemporaryDirectory(dir=destination) as temporary:
            staging = Path(temporary)
            with tarfile.open(ROOT/'sources'/item['archive']) as archive:
                archive.extractall(staging, filter='data')
            original = staging/'original'/item['original']
            if hashlib.sha256(original.read_bytes()).hexdigest() != item['original_sha256']:
                raise RuntimeError('Original source checksum mismatch: '+original.name)
            unpacked = staging/'tree'; unpacked.mkdir()
            with tarfile.open(original) as archive:
                archive.extractall(unpacked, filter='data')
            folders = list(unpacked.iterdir())
            if len(folders) != 1 or not folders[0].is_dir():
                raise RuntimeError('Unexpected original source layout: '+original.name)
            folders[0].rename(output)
            shutil.copytree(staging/'packaging/debian', output/'debian', dirs_exist_ok=True)
            subprocess.run(['dpkg-source', '--before-build', str(output)], check=True)
            if item['directory'] == 'hyprland-source':
                # GCC 14 lacks the C++26 string + string_view overload.
                path = output/'src/config/shared/parserUtils/ParserUtils.cpp'
                text = path.read_text(); old = 'std::string{"0x"} + value'
                if text.count(old) != 1: raise RuntimeError('Hyprland compatibility patch no longer applies.')
                path.write_text(text.replace(old, 'std::string{"0x"} + std::string(value)'))
            if item['directory'].startswith('kitty-'):
                shutil.copytree(staging/'vendor', output/'vendor', dirs_exist_ok=True)
                # Same module versions as the binary build, supplied offline.
                rules = output/'debian/rules'
                rules.write_text(rules.read_text().replace('-mod=mod', '-mod=vendor'))
                setup = output/'setup.py'
                setup.write_text(setup.read_text().replace('num_workers = max(2, os.cpu_count() or 1)',
                                                          'num_workers = min(3, max(2, os.cpu_count() or 1))'))
    with tarfile.open(ROOT/'sources/debian-backports-sources.tar.xz') as archive:
        archive.extractall(destination/'debian-backports', filter='data')
    return inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='New empty source output directory')
    parser.add_argument('--build', metavar='SOURCE', help='Build one prepared source directory with dpkg-buildpackage')
    parser.add_argument('--jobs', type=int, default=3)
    args = parser.parse_args()
    inputs = prepare(args.directory.resolve())
    print('Sources prepared in '+str(args.directory.resolve()))
    if args.build:
        if args.build not in {item['directory'] for item in inputs}: parser.error('Unknown source directory')
        env = {**os.environ, 'DEB_BUILD_OPTIONS':f'parallel={max(1,args.jobs)} nocheck nodoc',
               'DEB_BUILD_PROFILES':'noudeb nocheck nodoc', 'GIT_COMMIT_HASH':'efb50993780079460b0cbed1363e2166a2de1d9f',
               'GIT_TAG':'v0.56.2', 'GIT_BRANCH':'v0.56.2'}
        # Patches were applied above; avoid dpkg-source trying to apply them again.
        subprocess.run(['dpkg-buildpackage', '-b', '-nc', '-us', '-uc'], cwd=args.directory/args.build, env=env, check=True)


if __name__ == '__main__': main()
