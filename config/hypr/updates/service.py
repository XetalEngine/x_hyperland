#!/usr/bin/env python3
"""One session-owned update checker; Waybar only reads its cached status."""
from __future__ import annotations
import argparse
import fcntl
import html
import json
import os
from pathlib import Path
import random
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time

import github
import update_engine as engine
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'runtime'))
import runtime_policy

ROOT = Path(__file__).resolve().parents[1]
STATE = Path.home()/'.local/state/xetal-hyprland/updates'
CACHE = Path.home()/'.cache/xetal-hyprland/updates'
NOTICE_DELAY = 30


def preferences(state=None):
    state = state or STATE
    value = engine.json_file(state/'settings.json', {})
    return {'automatic': value.get('automatic', True) is True,
            'interval': max(300, min(86400, int(value.get('interval', 900))))}


def status(state=None, root=None):
    state = state or STATE
    value = engine.json_file(state/'status.json', {})
    # Direct development installs update the inventory while the session checker
    # stays alive. The installed revision wins over its cached failure/status.
    if root is None and state != STATE: return value
    try: current = engine.installed(root or ROOT)['revision']
    except (OSError, ValueError, RuntimeError): return value
    if value.get('phase') == 'rollback': return value
    if value.get('phase') == 'runtime-required' and current == value.get('current'): return value
    if current == value.get('latest') and value.get('phase') != 'checking':
        value.update(phase='current', current=current, failed_revision='', retry_prepare=False,
                     message='Your desktop is up to date.')
        value['github'] = {**value.get('github', {}), 'base':current, 'relation':'identical'}
    elif current != value.get('current'):
        value.update(phase='current', current=current, failed_revision='', retry_prepare=False,
                     message='Local desktop revision changed. Checking GitHub will refresh its status.')
        value['github'] = {**value.get('github', {}), 'relation':'unknown'}
    return value


def publish(state=None, **changes):
    state = state or STATE
    value = status(state); value.update(changes); engine.write_json(state/'status.json', value)
    return value


def request(action, state=None):
    state = state or STATE
    if action not in ('check', 'prepare', 'setup', 'rollback'): raise ValueError('Unknown update action.')
    engine.write_json(state/'request.json', {'action': action, 'time': time.time()})


def badge(value):
    phase = value.get('phase', 'current')
    labels = {'available': '↻ UPDATE', 'preparing': '↻ UPDATING', 'ready': '✓ UPDATE READY',
              'attention': '↻ UPDATE !', 'runtime-required': '↻ SETUP REQUIRED', 'rollback': '↶ ROLLBACK'}
    text = labels.get(phase, '')
    # No idle/checking icon, and no update notice for a connection error alone.
    if phase == 'attention' and not (value.get('github', {}).get('relation') == 'ahead'
                                    and value.get('latest') != value.get('current')):
        text = ''
    message = value.get('message', 'Xetal desktop updates · Click to check and manage updates')
    if value.get('prepared'): message += '\nPrepared desktop · '+value['prepared'][:8]
    if value.get('latest'): message += '\nGitHub main · '+value['latest'][:8]
    return {'text': text, 'class': phase, 'tooltip': html.escape(message)}


def check(root=None, state=None):
    root, state = root or ROOT, state or STATE
    current = engine.installed(root)['revision']; value = status(state, root)
    if time.time() < value.get('retry_at', 0): return value
    try:
        latest = github.latest(current, value.get('github'))
        pending = engine.json_file(state/'pending.json')
        prepared = pending and (pending.get('revision') == latest['sha'] or latest['relation'] != 'ahead')
        phase = 'ready' if prepared else 'available' if latest['relation'] == 'ahead' else 'current'
        message = ('Update prepared. It will activate at your next Hyprland login.' if prepared else
                   'A new Xetal desktop update is available.' if phase == 'available' else
                   'Your desktop is up to date.' if latest['relation'] == 'identical' else
                   'This build is ahead of main or has a different history. Automatic downgrades are disabled.')
        if pending and pending.get('rollback'): phase = 'rollback'; message = 'Rollback is queued for your next Hyprland login.'
        elif not pending and latest['relation'] == 'ahead' and value.get('failed_revision') == latest['sha']:
            phase = 'attention'; message = value.get('message', 'Update preparation needs attention.')
        required = engine.json_file(state/'runtime-required.json', {})
        if latest['sha'] == current and (root/'runtime/manifest.json').exists():
            local_problem = runtime_policy.problem(root)
            if local_problem:
                required = {'revision': current, 'required': runtime_policy.manifest(root)['hyprland'], 'message': local_problem}
                engine.write_json(state/'runtime-required.json', required)
            else:
                (state/'runtime-required.json').unlink(missing_ok=True); required = {}
        if required.get('revision') == latest['sha']:
            phase = 'runtime-required'; message = required['message']
        return publish(state, phase=phase, current=current, latest=latest['sha'], title=latest['message'],
                       github=latest, message=message, checked=time.time(), retry_at=0,
                       prepared=pending.get('revision','') if pending else '',
                       failed_revision=value.get('failed_revision','') if phase in ('attention','runtime-required') else '')
    except Exception as error:
        retry_at = getattr(error, 'retry_at', time.time()+900)
        phase = value.get('phase', 'current')
        if phase == 'checking': phase = 'available' if value.get('github', {}).get('relation') == 'ahead' else 'current'
        return publish(state, message='Could not check GitHub: '+str(error), checked=time.time(), retry_at=retry_at,
                       phase=phase)


def worker(commit, manual=False, setup=False):
    os.nice(10)
    with tempfile.TemporaryDirectory(prefix='download-', dir=STATE) as temporary:
        print('Downloading GitHub main commit '+commit[:8]+'…', flush=True)
        source = github.source(commit, CACHE, Path(temporary)/'source')
        if setup:
            args = [sys.executable, str(source/'installer/launcher.py'), '--gui', '--update']
        else:
            args = [sys.executable, str(source/'installer/update.py'), '--revision', commit]
            if manual: args.append('--manual')
        subprocess.run(args, check=True)


def queue_rollback(root=None, state=None):
    root, state = root or ROOT, state or STATE
    with engine.locked(state):
        record = engine.json_file(state/'last-backup.json')
        if not record: raise RuntimeError('There is no completed update to roll back yet.')
        backup = Path(record['backup']); plan = engine.rollback_plan(root, backup)
        required = plan.get('runtime')
        if required and (runtime_policy.installed()['version'] != required['hyprland'] or
                         runtime_policy.installed()['commit'] != required['commit']):
            raise RuntimeError('This backup requires Hyprland '+required['hyprland']+'. Use Setup for that desktop release to restore the compositor and profile together.')
        engine.check_plan(root, backup/'files', plan)
        engine.write_json(state/'rollback-plan.json', plan)
        engine.write_json(state/'pending.json', {'stage': str(backup/'files'), 'plan': str(state/'rollback-plan.json'),
                                               'revision': plan['revision'], 'automatic': False, 'rollback': True})
        settings = preferences(state); settings['automatic'] = False; engine.write_json(state/'settings.json', settings)
        publish(state, phase='rollback', message='Rollback is queued for your next Hyprland login. Automatic updates are paused.')


def activate(root=None, state=None):
    root, state = root or ROOT, state or STATE
    with engine.locked(state):
        engine.recover(root, state)
        pending = engine.json_file(state/'pending.json')
        if not pending or (pending.get('automatic') and not preferences(state)['automatic']): return False
        stage = Path(pending['stage'])
        if not stage.resolve().is_relative_to(state.resolve()): raise ValueError('Prepared update is outside its private state directory.')
        if (engine.installed(root)['revision'] == pending['revision'] and
                not pending.get('rollback') and not pending.get('runtime_setup')):
            (state/'pending.json').unlink(); return False
        plan = engine.json_file(Path(pending.get('plan', str(stage/'plan.json'))))
        try:
            if pending.get('rollback'):
                required = plan.get('runtime')
                actual = runtime_policy.installed()
                if required and (actual['version'] != required['hyprland'] or actual['commit'] != required['commit']):
                    raise RuntimeError('The queued backup requires a different compositor. Use Setup to restore its matching version.')
            elif (stage/'runtime/manifest.json').exists():
                message = runtime_policy.problem(stage)
                if message:
                    engine.write_json(state/'runtime-required.json', {'revision':pending['revision'],
                        'required':runtime_policy.manifest(stage)['hyprland'], 'message':message})
                    publish(state, phase='runtime-required', current=engine.installed(root)['revision'],
                            latest=pending['revision'], message=message, failed_revision=pending['revision'])
                    return False
            elif (root/'runtime/manifest.json').exists():
                raise RuntimeError('This prepared update predates compositor version management. Prepare the latest desktop release again.')
            engine.check_plan(root, stage, plan)
            if not pending.get('rollback'):
                with tempfile.TemporaryDirectory(prefix='verify-', dir=state) as directory:
                    sys.path.insert(0, str(stage/'compat'))
                    import hypr_compat
                    candidate = hypr_compat.candidate(stage, directory)
                    checked = subprocess.run(['Hyprland', '--verify-config', '--config', str(candidate)], capture_output=True, text=True, timeout=30)
                    if checked.returncode or 'config ok' not in checked.stdout:
                        raise RuntimeError('This update needs preparation for the current Hyprland version. Your desktop was kept.')
        except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
            (state/'pending.json').unlink()
            publish(state, phase='attention', message=str(error), retry_prepare=True)
            return False
        backup = engine.apply_plan(root, stage, plan, state)
        (state/'pending.json').unlink(missing_ok=True)
        (state/'runtime-required.json').unlink(missing_ok=True)
        publish(state, phase='current', current=plan['revision'], installed=engine.now(),
                message='Desktop update installed.' if not pending.get('rollback') else 'Previous desktop version restored.',
                backup=str(backup), retry_prepare=False, failed_revision='')
        return True


def take_request(state=None):
    state = state or STATE
    path = state/'request-handled.json'
    try: os.replace(state/'request.json', path)
    except FileNotFoundError: return None
    command = engine.json_file(path, {})
    return command.get('action') if time.time()-command.get('time', 0) < 300 else None


def stop_worker(process):
    """Stop only this worker and its compiler descendants, even separate groups."""
    if process is None or process.poll() is not None: return
    handles = []
    def freeze(pid):
        try:
            handle = os.pidfd_open(pid); signal.pidfd_send_signal(handle, signal.SIGSTOP)
            handles.append(handle)
            for child in (Path('/proc')/str(pid)/'task'/str(pid)/'children').read_text().split(): freeze(int(child))
        except (OSError, ValueError): pass
    freeze(process.pid)
    for handle in reversed(handles):
        try: signal.pidfd_send_signal(handle, signal.SIGKILL)
        except OSError: pass
        finally: os.close(handle)
    try: process.wait(timeout=3)
    except subprocess.TimeoutExpired: pass


def serve():
    signature = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    if not signature: return
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))/'hypr'/signature
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (STATE/'daemon.lock').open('a') as lock, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as session:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        session.connect(str(runtime/'.socket2.sock')); session.setblocking(False)
        process = None; log = None; running_revision = ''; role = ''; started = time.time()
        next_check = time.time()+random.uniform(35, 70); available_since = None
        def stop(*_): raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
        try:
            while True:
                ready, _, _ = select.select([session], [], [], 1)
                if ready:
                    try:
                        if not session.recv(65536): break
                    except BlockingIOError: pass
                settings = preferences(); action = take_request()
                if process and process.poll() is not None:
                    code = process.returncode; process = None
                    if log: log.close(); log = None
                    if role == 'check':
                        next_check = max(time.time()+settings['interval'], status().get('retry_at', 0))
                    elif code == 0:
                        if engine.installed(ROOT)['revision'] == running_revision:
                            publish(phase='current', current=running_revision, message='Desktop installed. Log out and sign in to start it.', failed_revision='', prepared='')
                        else:
                            publish(phase='ready', message='Update prepared. It will activate at your next Hyprland login.', failed_revision='', prepared=running_revision)
                    else:
                        lines = (STATE/'update.log').read_text(errors='replace').strip().splitlines()
                        detail = next((x for x in reversed(lines) if not x.startswith(('Traceback', '  File', 'subprocess.'))), 'See the update log.')
                        required = engine.json_file(STATE/'runtime-required.json', {})
                        if required.get('revision') == running_revision:
                            publish(phase='runtime-required', message=required['message'], failed_revision=running_revision)
                        else:
                            publish(phase='attention', message='Update preparation stopped. '+detail[-800:], failed_revision=running_revision)
                if process: continue
                if action == 'rollback':
                    try: queue_rollback()
                    except Exception as error: publish(phase='attention', message=str(error))
                    continue
                value = status()
                if action == 'check' or time.time() >= next_check:
                    if time.time() < value.get('retry_at', 0):
                        next_check = value['retry_at']
                    else:
                        role = 'check'; log = (STATE/'check.log').open('w')
                        if value.get('phase', 'current') == 'current': publish(phase='checking', message='Checking GitHub…')
                        process = subprocess.Popen([sys.executable, str(Path(__file__)), '--check'],
                                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                        continue
                pending = engine.json_file(STATE/'pending.json')
                if pending and (pending.get('rollback') or pending.get('revision') == value.get('latest')) and action != 'setup': continue
                eligible = value.get('latest') and (value.get('github', {}).get('relation') == 'ahead' or action == 'setup')
                if eligible and available_since is None: available_since = time.time()
                if not eligible: available_since = None; continue
                automatic = (settings['automatic'] and value.get('failed_revision') != value['latest']
                             and value.get('checked', 0) >= started and time.time()-available_since >= NOTICE_DELAY)
                if action in ('prepare', 'setup') or automatic:
                    role = 'prepare'
                    running_revision = engine.revision(value['latest'])
                    publish(phase='preparing', message='Downloading, merging and validating the new desktop…', retry_prepare=False)
                    log = (STATE/'update.log').open('w')
                    args = [sys.executable, str(Path(__file__)), '--worker', running_revision]
                    if action == 'prepare': args.append('--manual')
                    if action == 'setup': args.append('--setup')
                    process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        except (KeyboardInterrupt, ConnectionError): pass
        finally:
            if process and process.poll() is None:
                stop_worker(process)
                publish(phase='available' if role == 'prepare' else 'current',
                        message='Update work paused at logout. It will resume next session.')
            if log: log.close()


def main():
    parser = argparse.ArgumentParser(); mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--serve', action='store_true'); mode.add_argument('--status', action='store_true')
    mode.add_argument('--activate', action='store_true'); mode.add_argument('--worker')
    mode.add_argument('--check', action='store_true'); parser.add_argument('--manual', action='store_true')
    parser.add_argument('--setup', action='store_true')
    args = parser.parse_args()
    try:
        if args.status: print(json.dumps(badge(status()))); return 0
        if args.serve: serve()
        elif args.activate: return 20 if activate() else 0
        elif args.worker: worker(engine.revision(args.worker), args.manual, args.setup)
        elif args.check: print(json.dumps(check(), indent=2))
        return 0
    except Exception as error:
        print(str(error), file=sys.stderr)
        if not args.status: publish(phase='attention', message=str(error))
        return 1


if __name__ == '__main__': sys.exit(main())
