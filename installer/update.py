#!/usr/bin/env python3
"""Prepare a settings-preserving update; activation is a separate login step."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import install
import dependencies
sys.path.insert(0, str(install.PAYLOAD/'updates'))
import update_engine as engine


def prepare(home, commit, automatic=True):
    if os.geteuid() == 0: raise RuntimeError('Updates run as your desktop user, without sudo.')
    install.safe_home(home); engine.revision(commit)
    actual = subprocess.check_output(['git', '-C', str(install.REPO), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != commit: raise RuntimeError('Downloaded source does not match the announced commit.')
    errors = dependencies.check()
    if errors: raise RuntimeError('Dependencies need attention; no files changed:\n'+'\n'.join(errors))
    live = home/'.config/hypr'; state = home/'.local/state/xetal-hyprland/updates'
    with engine.locked(state):
        engine.recover(live, state)
        with tempfile.TemporaryDirectory(prefix='prepare-', dir=state) as temporary:
            root = Path(temporary); upstream = root/'upstream'; stage = root/'profile'
            print('Merging the new desktop with your settings…', flush=True)
            install.render(upstream, home, install.connected_monitors())
            expected = engine.merge_profile(live, upstream, stage, commit)
            # These paths are not source-controlled and are created by the initial installer.
            for directory in ('dolphin/cache', 'dolphin/state', 'apps', 'assets/font-cache'):
                (stage/directory).mkdir(parents=True, exist_ok=True)
            print('Building desktop components for this computer…', flush=True)
            install.build(stage)
            subprocess.run([sys.executable, str(stage/'theme/update_widget.py')], check=True)
            print('Validating the complete prepared configuration…', flush=True)
            install.validate(stage)
            plan = engine.prepare_plan(live, stage, expected, commit, automatic)
            engine.check_plan(live, stage, plan)
            destination = state/('prepared-'+commit)
            if destination.exists(): shutil.rmtree(destination)
            os.replace(stage, destination)
            engine.write_json(destination/'plan.json', plan)
            engine.write_json(state/'pending.json', {'stage': str(destination), 'revision': commit,
                                                     'automatic': automatic})
            print('Ready. This update will activate at your next Hyprland login.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--revision', required=True)
    parser.add_argument('--manual', action='store_true'); args = parser.parse_args()
    try: prepare(Path.home(), args.revision, not args.manual)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr); sys.exit(1)
