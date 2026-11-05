#!/usr/bin/env python3
"""Check first-frame notices across repeated disposable compositor launches.

Run inside a Wayland session: python3 tests/check-startup-notices.py OUTPUT_DIR
No IPC command is sent to the user's compositor; every target is matched by PID.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'installer'))
from system_login import configuration


def main():
    root = Path(sys.argv[1]).resolve()
    root.mkdir(parents=True, exist_ok=False)
    adapter = subprocess.check_output([sys.executable, str(REPO/'config/hypr/runtime/notices/build.py')], text=True).strip()
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'hyprland', 'libeis-1.0'], text=True))
    probe = root/'probe.so'
    subprocess.run(['g++', '-std=c++23', '-shared', '-fPIC', '-O2', *flags,
                    str(REPO/'tests/native/startup_notices_probe.cpp'), '-o', str(probe)], check=True)
    hyprland, hyprctl = shutil.which('Hyprland'), shutil.which('hyprctl')
    results = []
    for index in range(5):
        # The control run proves both upstream notices are actually present.
        enabled = index != 0
        home = root/str(index); home.mkdir()
        (home/'bin').mkdir()
        conf = home/'hyprland.conf'
        text = f'''monitor = ,800x600@60,auto,1
misc:disable_hyprland_logo = true
misc:disable_splash_rendering = true
misc:disable_hyprland_guiutils_check = {'true' if enabled else 'false'}
xwayland:enabled = false
debug:disable_logs = false
plugin = {probe}
'''
        if enabled:
            text += f'plugin = {adapter}\n'
        if index == 3:
            text += 'general:fusion_test_invalid_setting = 1\n'
        if index == 4:
            # Exercise the actual installer-owned greeter config, not a second
            # hand-written approximation. Do not launch a real login service.
            text = 'plugin = '+str(probe)+'\n'+configuration()[Path('/etc/xetal-fusion-login/hyprland.conf')]
            text = text.replace('/usr/local/lib/xetal-fusion-login/xetal-startup-notices.so', adapter)
            text = text.replace('exec-once = /usr/local/lib/xetal-fusion-login/greeter-session.sh', '# No real greeter in this isolated compositor check.')
            text += '\nxwayland:enabled = false\ndebug:disable_logs = false\n'
        conf.write_text(text)
        env = dict(os.environ)
        env.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
        env.update(AQ_BACKENDS='wayland', HOME=str(home), XDG_CONFIG_HOME=str(home/'.config'),
                   XDG_CACHE_HOME=str(home/'.cache'), XDG_DATA_HOME=str(home/'.local/share'),
                   HYPRLAND_NO_SD_VARS='1', HYPRLAND_NO_SD_NOTIFY='1', GSETTINGS_BACKEND='memory',
                   # Ensure the missing-guiutils check is exercised on every host.
                   PATH=str(home/'bin'), LANG='pt_BR.UTF-8' if index == 2 else 'en_US.UTF-8')
        with (home/'compositor.log').open('w') as log:
            compositor = subprocess.Popen([hyprland, '--config', str(conf)], env=env,
                                          stdout=log, stderr=log, start_new_session=True)
            try:
                for _ in range(100):
                    assert compositor.poll() is None, 'Compositor exited: '+str(home/'compositor.log')
                    instances = json.loads(subprocess.check_output([hyprctl, '-j', 'instances'], text=True))
                    instance = next((i for i in instances if i['pid'] == compositor.pid), None)
                    if instance:
                        env.update(HYPRLAND_INSTANCE_SIGNATURE=instance['instance'], WAYLAND_DISPLAY=instance['wl_socket'])
                        break
                    time.sleep(.1)
                else:
                    raise AssertionError('No disposable compositor instance')
                def ctl(*args):
                    return subprocess.check_output([hyprctl, *args], env=env, text=True, timeout=10).strip()
                for _ in range(100):
                    state = json.loads(ctl('fusion-notices-probe'))
                    if state['frames'] > 0:
                        break
                    time.sleep(.05)
                assert state['frames'] > 0, state
                for key in ('config', 'gui', 'first_config', 'first_gui', 'max_config', 'max_gui'):
                    assert state[key] == (0 if enabled else 1), (key, state)
                assert state['warning'] == 1 and state['error'] == 1, state
                errors = ctl('configerrors')
                assert ('fusion_test_invalid_setting' in errors) == (index == 3), errors
                assert ctl('reload') == 'ok'
                time.sleep(.2)
                after = json.loads(ctl('fusion-notices-probe'))
                assert after['warning'] == 1 and after['error'] == 1, after
                assert after['config'] == state['config'] and after['gui'] == state['gui'], after
                results.append({'launch': index, 'greeter_config': index == 4,
                                'filtered': enabled, 'locale': env['LANG'], **state})
                print(json.dumps(results[-1]), flush=True)
                ctl('dispatch', 'exit')
                compositor.wait(timeout=10)
            finally:
                if compositor.poll() is None:
                    compositor.terminate()
                    try: compositor.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        compositor.kill(); compositor.wait()
    (root/'results.json').write_text(json.dumps(results, indent=2)+'\n')


if __name__ == '__main__':
    main()
