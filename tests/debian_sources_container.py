#!/usr/bin/env python3
"""Reproduce DVD-only APT failures using real Debian metadata in private APT paths."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'installer'))
import debian_runtime as debian
import debian_sources as sources
import dependencies
import runtime_install as runtime

DVD = 'deb cdrom:[Debian GNU/Linux 13.7.0 _Trixie_ - Official amd64 DVD Binary-1 with firmware 20260912-09:36]/ trixie contrib main non-free-firmware\n'


def main():
    if os.environ.get('XETAL_DISPOSABLE_DEBIAN') != '1' or os.geteuid() != 0 or not runtime.policy.debian_host():
        raise SystemExit('Requires root inside disposable Debian 13 and XETAL_DISPOSABLE_DEBIAN=1; never run on a desktop host.')
    with tempfile.TemporaryDirectory(prefix='xetal-dvd-test-') as temp:
        root = Path(temp); root.chmod(0o755)
        apt = root/'apt'; (apt/'sources.list.d').mkdir(parents=True)
        lists = root/'lists'; lists.mkdir()
        state = root/'backups'
        private = ['-o', 'Dir::Etc::sourcelist='+str(apt/'sources.list'),
                   '-o', 'Dir::Etc::sourceparts='+str(apt/'sources.list.d'),
                   '-o', 'Dir::State::lists='+str(lists),
                   '-o', 'Dir::Cache::pkgcache='+str(root/'pkgcache'),
                   '-o', 'Dir::Cache::srcpkgcache='+str(root/'srcpkgcache')]
        with patch.object(debian, 'APT', [*debian.APT, *private]):
            original = apt/'sources.list'; original.write_text(DVD)
            failed = subprocess.run([*debian.APT, '-q', '-o', 'APT::Update::Error-Mode=any', 'update'],
                                    capture_output=True, text=True, env=debian.ENV)
            assert failed.returncode == 100, failed.stdout+failed.stderr
            assert 'cdrom:' in failed.stdout+failed.stderr
            assert 'Release file' in failed.stderr
            print('Reproduced the DVD-only APT Release-file failure.', flush=True)

            assert sources.refresh(apt, state) == 0
            before = sources.read_sources(apt)
            backup = next(path for path in state.iterdir() if path.is_dir())
            assert (backup/'sources.list').read_text() == DVD
            added = apt/'sources.list.d/xetal-debian.sources'
            assert added.exists() and 'Signed-By:' in added.read_text()
            # All real dependency names and native DEBs must resolve against the
            # freshly downloaded indexes, including those missing in the report.
            debian.preflight(dependencies.PACKAGES['debian'])
            assert sources.refresh(apt, state) == 0
            assert sources.read_sources(apt) == before
            assert len([path for path in state.iterdir() if path.is_dir()]) == 1
            print('DVD-only source repair, native dependency resolution and idempotent retry passed.', flush=True)

            # Modern deb822 input must also work when APT itself reads it, not
            # just in a parser fixture. Preserve the already selected mirrors.
            original.unlink()
            media = apt/'sources.list.d/install-media.sources'
            media.write_text('Types: deb\nURIs: cdrom:[Debian install DVD]/\nSuites: trixie\nComponents: main\n')
            saved_online = added.read_bytes()
            assert sources.refresh(apt, state) == 0
            assert 'Enabled: no' in media.read_text()
            assert added.read_bytes() == saved_online
            assert sources.refresh(apt, state) == 0
            print('deb822 installation-media repair passed with real APT.', flush=True)

            # Do not hide unrelated repository failures or publish a half-tested
            # source repair. This local missing Release file fails deterministically.
            media.unlink(); added.unlink(); original.write_text(DVD)
            bad = apt/'sources.list.d/broken.list'
            bad.write_text('deb [trusted=no] file:'+str(root/'missing-repository')+' vendor main\n')
            before = sources.read_sources(apt)
            assert sources.refresh(apt, state) == 100
            assert sources.read_sources(apt) == before
            assert not added.exists()
            print('An unrelated repository failure preserved the original source files.', flush=True)
    print(json.dumps(dict(distribution='Debian 13', dvd_failure_reproduced=True, source_repair=True,
                          dependency_resolution=True, deb822=True, idempotent=True, failed_refresh_preserved_sources=True)))


if __name__ == '__main__': main()
