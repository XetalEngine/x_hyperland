#!/usr/bin/env python3
"""Check actual Cube sky pixels in a disposable nested Wayland compositor.

Usage: python3 tests/check-cube-sky.py /path/to/xetal-cube.so /tmp/new-test-dir [old-plugin.so]
Never loads a plugin into the parent/working compositor. Needs a Wayland session,
Hyprland, grim and the repository's normal Pillow dependencies.
"""
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import time
from PIL import Image, ImageChops, ImageStat

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'config/hypr'))
from effects.cube import model


def main():
    binary = Path(sys.argv[1]).resolve(strict=True)
    root = Path(sys.argv[2]).resolve(); root.mkdir(parents=True, exist_ok=False)
    # A deterministic picture with detail everywhere, including the test corner.
    picture = Image.new('RGB', (1280, 800))
    picture.putdata([(30+x*180//1280, 30+y*180//800, 50+(x//37+y//29)%2*130)
                     for y in range(800) for x in range(1280)])
    picture.save(root/'picture.png')
    values = model.validate(model.DEFAULTS)
    values.update(zoom=.25, duration=0, sky_mode='image', sky_motion=True,
                  sky_speed=0, windows_3d=False, wall_opacity=0)
    values['sky_image'] = model.import_image(root/'picture.png', root)
    model.prepare_images(values, root)
    config = root/'settings.json'; config.write_text(model.encode(values))
    (root/'hyprland.conf').write_text('''monitor = ,1280x800@60,auto,1
misc {
    disable_hyprland_logo = true
    disable_splash_rendering = true
    background_color = rgb(181c26)
}
xwayland {
    enabled = false
}
animations {
    enabled = false
}
''')
    env = dict(os.environ); env.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
    env.update(AQ_BACKENDS='wayland', XETAL_CUBE_CONFIG=str(config))
    with (root/'compositor.log').open('w') as log:
        compositor = subprocess.Popen(['Hyprland', '--config', str(root/'hyprland.conf')],
                                      env=env, stdout=log, stderr=log, start_new_session=True)
        try:
            for _ in range(100):
                if compositor.poll() is not None: raise RuntimeError('Nested compositor did not start; see compositor.log')
                instances = json.loads(subprocess.check_output(['hyprctl', '-j', 'instances'], text=True))
                instance = next((i for i in instances if i['pid'] == compositor.pid), None)
                if instance:
                    env.update(HYPRLAND_INSTANCE_SIGNATURE=instance['instance'], WAYLAND_DISPLAY=instance['wl_socket'])
                    break
                time.sleep(.1)
            else: raise RuntimeError('Nested compositor instance was not found')
            # Every command below is explicitly addressed to this new instance.
            def run(*args):
                result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=15)
                if result.returncode: raise RuntimeError(str(args)+result.stdout+result.stderr)
                return result.stdout.strip()
            def dispatch(*args):
                answer = run('hyprctl', 'dispatch', *args)
                assert answer == 'ok', (args, answer)
            def status(): return json.loads(run('hyprctl', 'xetal-cube'))
            def capture(name, monitor):
                path = root/(name+'.png'); run('grim', '-o', monitor, str(path))
                with Image.open(path) as image: return image.convert('RGB')
            def difference(a, b):
                # Above and left of the small central cube and its labels.
                box = (24, 24, min(240, a.width//3), min(140, a.height//4))
                return sum(ImageStat.Stat(ImageChops.difference(a.crop(box), b.crop(box))).mean)/3
            def configure(mode, follow, speed):
                values.update(sky_mode=mode, sky_motion=follow, sky_speed=speed)
                config.write_text(model.encode(values)); dispatch('xetalcube:reload')
            def begin(monitor):
                dispatch('xetalcube:preview', monitor); time.sleep(.22)
                assert status()['active'], status()
            def finish():
                dispatch('xetalcube:finish', 'cancel'); time.sleep(.15)
                assert not status()['active'], status()
            time.sleep(.5)
            if len(sys.argv) > 3:
                old = Path(sys.argv[3]).resolve(strict=True)
                assert run('hyprctl', 'plugin', 'load', str(old)) == 'ok'
                assert status()['enabled']
                begin(''); finish()
                assert run('hyprctl', 'plugin', 'unload', str(old)) == 'ok'
            assert run('hyprctl', 'plugin', 'load', str(binary)) == 'ok'
            run('hyprctl', 'output', 'create', 'wayland'); time.sleep(.3)
            outputs = json.loads(run('hyprctl', '-j', 'monitors'))
            assert len(outputs) == 2, outputs
            monitors = [m['name'] for m in outputs]
            for monitor in monitors:
                other = next(m for m in monitors if m != monitor)
                untouched = capture('other-before-'+monitor, other)
                for mode in ('image', 'sky'):
                    for follow in (False, True):
                        name = f'{monitor}-{mode}-{follow}'
                        configure(mode, follow, 0); begin(monitor)
                        before = capture(name+'-before', monitor)
                        dispatch('xetalcube:turn', '140 -85'); time.sleep(.15)
                        after = capture(name+'-after', monitor)
                        delta = difference(before, after)
                        print(name, 'rotation difference:', round(delta, 3), flush=True)
                        assert delta > 2 if follow else delta < .2, (name, delta)
                        finish()
                    configure(mode, False, 20); begin(monitor)
                    before = capture(f'{monitor}-{mode}-drift-before', monitor); time.sleep(.6)
                    after = capture(f'{monitor}-{mode}-drift-after', monitor)
                    delta = difference(before, after)
                    print(monitor, mode, 'independent drift difference:', round(delta, 3), flush=True)
                    assert delta > 1, (mode, 'drift', delta)
                    finish()
                assert difference(untouched, capture('other-after-'+monitor, other)) < .2
            configure('image', True, 0); begin(monitors[0])
            before = capture('full-turn-before', monitors[0])
            dispatch('xetalcube:turn', f'{360/values["sensitivity"]} 0'); time.sleep(.15)
            assert difference(before, capture('full-turn-after', monitors[0])) < .2
            finish()
            answer = run('hyprctl', 'keyword', 'monitor', f'{monitors[0]},1280x800@60,0x0,1.25,transform,1')
            assert answer == 'ok', answer
            time.sleep(.3); begin(monitors[0]); before = capture('portrait-before', monitors[0])
            dispatch('xetalcube:turn', '140 -85'); time.sleep(.15)
            assert difference(before, capture('portrait-after', monitors[0])) > 2
            assert not status()['error'], status()
            assert run('hyprctl', 'plugin', 'unload', str(binary)) == 'ok'
            # A different pathname/inode exercises replacement, not reuse of
            # the same cached module. JSON must survive repeated load cycles.
            for i in range(3):
                replacement = root/f'reload-{i}.so'; shutil.copy2(binary, replacement)
                assert run('hyprctl', 'plugin', 'load', str(replacement)) == 'ok'
                assert status()['enabled']; begin(monitors[0])
                assert not status()['error'], status()
                assert run('hyprctl', 'plugin', 'unload', str(replacement)) == 'ok'
            print('PASS: picture/panorama on/off, drift, two monitors, full turn, rotated/scaled output, active unload and replacement builds', flush=True)
        finally:
            if compositor.poll() is None: compositor.terminate()
            try: compositor.wait(timeout=8)
            except subprocess.TimeoutExpired: compositor.kill(); compositor.wait()


if __name__ == '__main__': main()
