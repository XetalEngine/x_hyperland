#!/usr/bin/env python3
"""Check login and reload environment in a disposable nested Hyprland instance.

Unlike --verify-config, a real startup applies env directives. The parent
desktop is never reloaded; only the test compositor and its capture helper run.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def check(environment):
    parent = Path(os.environ['WAYLAND_DISPLAY'])
    if not parent.is_absolute(): parent = Path(os.environ['XDG_RUNTIME_DIR'])/parent
    # Unix socket pathnames include Hyprland's long instance signature.
    with tempfile.TemporaryDirectory(prefix='fe-') as temporary:
        root = Path(temporary)
        runtime = root/'r'; runtime.mkdir(mode=0o700)
        home = root/'home'; home.mkdir()
        rendered = root/'environment.conf'
        rendered.write_text(environment.read_text().replace('@HOME@', str(home)).replace('@HYPR@', str(ROOT/'config/hypr')))
        capture = root/'capture.py'
        result = root/'environment.json'
        capture.write_text('import json,os,sys,shutil\nfrom pathlib import Path\n'
                           'target=Path('+repr(str(result))+')\npart=target.with_suffix(".tmp")\n'
                           'part.write_text(json.dumps(dict(path=os.environ.get("PATH"),'
                           'python=sys.executable,hyprctl=shutil.which("hyprctl"))))\npart.replace(target)\n')
        config = root/'hyprland.conf'
        config.write_text('monitor = ,800x500@60,auto,1\n'
                          'misc {\n disable_hyprland_logo = true\n disable_splash_rendering = true\n}\n'
                          'xwayland {\n enabled = false\n}\n'
                          'source = '+str(rendered)+'\nexec = /usr/bin/python3 '+str(capture)+'\n')
        env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY=str(parent))
        env.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
        compositor = None
        log = root/'compositor.log'
        with log.open('w') as stream:
            try:
                compositor = subprocess.Popen(['Hyprland', '-c', str(config)], env=env,
                                              stdout=stream, stderr=stream, start_new_session=True)
                deadline = time.monotonic()+20
                instance = None
                while time.monotonic() < deadline:
                    if compositor.poll() is not None: raise RuntimeError('Test compositor exited:\n'+log.read_text()[-6000:])
                    sockets = list(runtime.glob('hypr/*/.socket.sock'))
                    if sockets and result.exists(): instance=sockets[0].parent.name; break
                    time.sleep(.1)
                if not instance: raise RuntimeError('Login capture did not start:\n'+log.read_text()[-6000:])
                env['HYPRLAND_INSTANCE_SIGNATURE'] = instance
                def ctl(*args):
                    answer = subprocess.run(['/usr/bin/hyprctl', *args], env=env, capture_output=True, text=True, timeout=10)
                    if answer.returncode: raise RuntimeError(answer.stderr or answer.stdout)
                    return answer.stdout.strip()
                # Repeat reloads: a self-referential PATH can also keep growing
                # between reloads, even when initial validation reports success.
                captures = []
                for attempt in range(3):
                    errors = ctl('configerrors')
                    if errors: raise RuntimeError(errors)
                    captures.append(json.loads(result.read_text()))
                    if attempt < 2:
                        result.unlink(); ctl('reload')
                        deadline = time.monotonic()+5
                        while not result.exists() and time.monotonic() < deadline: time.sleep(.05)
                        if not result.exists(): raise RuntimeError('Reload capture did not start.')
                for data in captures:
                    if data['path'] != env['PATH']:
                        raise RuntimeError('Login changed the inherited command search path.')
                    if not data['python'] or not data['hyprctl']:
                        raise RuntimeError('Login lost the Python interpreter or Hyprland command.')
                print('PASS: real compositor login and two reloads; PATH preserved, Python and hyprctl available.')
            finally:
                if compositor and compositor.poll() is None:
                    compositor.terminate()
                    try: compositor.wait(timeout=5)
                    except subprocess.TimeoutExpired: compositor.kill(); compositor.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', type=Path, default=ROOT/'config/hypr/desktop/environment.conf')
    args = parser.parse_args()
    try: check(args.environment)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error)); raise SystemExit(1)
