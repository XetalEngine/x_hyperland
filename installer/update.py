#!/usr/bin/env python3
"""Prepare an update; foreground Setup coordinates compositor and activation."""
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


def prepare(home, commit, automatic=True, allow_runtime=False, checkpoint=lambda:None):
    if os.geteuid() == 0: raise RuntimeError('Updates run as your desktop user, without sudo.')
    install.safe_home(home); engine.revision(commit)
    actual = install.source_revision()
    if actual != commit: raise RuntimeError('Downloaded source does not match the announced commit.')
    live = home/'.config/hypr'; state = home/'.local/state/xetal-hyprland/updates'
    message = install.runtime_install.policy.problem()
    if message and not allow_runtime:
        with engine.locked(state):
            engine.write_json(state/'runtime-required.json', {'revision':commit,
                'required':install.runtime_install.policy.manifest()['hyprland'], 'message':message})
            (state/'pending.json').unlink(missing_ok=True)
        raise RuntimeError(message)
    if allow_runtime:
        dependencies.prepare_repositories()
        dependencies.preflight()
        install.runtime_install.ensure(yes=True)
        checkpoint()
    errors = dependencies.check()
    if errors and allow_runtime:
        dependencies.install(yes=True); checkpoint(); errors = dependencies.check()
    if errors: raise RuntimeError('Dependencies need attention; no desktop files changed:\n'+'\n'.join(errors))
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
            install.validate_config(stage)
            install.build(stage, checkpoint)
            subprocess.run([sys.executable, str(stage/'theme/update_widget.py')], check=True)
            print('Validating the complete prepared configuration…', flush=True)
            install.validate(stage)
            checkpoint()
            plan = engine.prepare_plan(live, stage, expected, commit, automatic)
            engine.check_plan(live, stage, plan)
            destination = state/('prepared-'+commit)
            if destination.exists(): shutil.rmtree(destination)
            os.replace(stage, destination)
            engine.write_json(destination/'plan.json', plan)
            engine.write_json(state/'pending.json', {'stage': str(destination), 'revision': commit,
                                                     'automatic': automatic, 'runtime_setup': allow_runtime})
            (state/'runtime-required.json').unlink(missing_ok=True)
            print('Ready. '+('Installing the matching desktop now.' if allow_runtime else
                            'This update will activate at your next Hyprland login.'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--revision', required=True)
    parser.add_argument('--manual', action='store_true')
    parser.add_argument('--runtime', action='store_true', help='Open administrator authentication for the matching compositor.')
    parser.add_argument('--activate', action='store_true', help='Activate a reviewed coordinated update before the next login.')
    parser.add_argument('--cancel-file', type=Path); args = parser.parse_args()
    def checkpoint():
        if args.cancel_file and args.cancel_file.exists(): raise RuntimeError('Update cancelled after completing the current step.')
    try:
        if (args.runtime or args.activate) and not args.manual: raise ValueError('Compositor changes require a foreground Setup request.')
        if args.runtime and not args.activate: raise ValueError('A compositor change must activate its matching desktop in the same Setup run.')
        prepare(Path.home(), args.revision, not args.manual, args.runtime, checkpoint)
        if args.activate:
            checkpoint()
            import service
            if not service.activate(Path.home()/'.config/hypr'):
                raise RuntimeError('Update was prepared but could not be activated. Open Desktop Updates for details.')
            install.runtime_install.complete()
            print('Installed. Log out and sign in again to start the matching compositor and desktop.', flush=True)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        install.runtime_install.rollback()
        print(str(error), file=sys.stderr); sys.exit(1)
