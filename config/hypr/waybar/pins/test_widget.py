"""Run via xvfb-run -a env GDK_BACKEND=x11 python test_widget.py.

Real pointer events exercise GTK drag/drop; only temporary mock apps are used.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent


def wait_for(predicate, message):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = predicate()
        if value: return value
        time.sleep(.05)
    raise AssertionError(message)


def run():
    with tempfile.TemporaryDirectory(prefix='xetal-pins-test-') as temporary:
        path = Path(temporary)
        state = path/'bar-pins.json'
        state.write_text(json.dumps({'version': 1, 'pins': ['a', 'b', 'c']}))
        helper = path/'helper.py'
        helper.write_text('''import json,sys
from pathlib import Path
sys.path.insert(0, %r)
import pins
pins.STATE=Path(__file__).with_name('bar-pins.json')
action=sys.argv[1]
if action=='list':
    print(json.dumps([{'id':i,'name':i.upper(),'icon':'utilities-terminal','available':True} for i in pins.pinned()]))
elif action=='move':pins.move(sys.argv[2],sys.argv[3],sys.argv[4]=='after')
elif action=='unpin':pins.pin(sys.argv[2],False)
elif action in ('left','right'):pins.step(sys.argv[2],-1 if action=='left' else 1)
else:
    with Path(__file__).with_name('actions.log').open('a') as log:log.write(' '.join(sys.argv[1:])+'\\n')
''' % str(ROOT.parents[1]/'launcher'))
        binary = path/'widget-test'
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'gtk+-3.0', 'json-glib-1.0'], text=True))
        subprocess.run(['cc', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', str(ROOT/'test-widget.c'), '-o', str(binary), *flags], check=True)
        log = (path/'widget.log').open('w+')
        proc = subprocess.Popen([str(binary), str(helper)], stdout=log, stderr=log)
        def xdo(*args):
            return subprocess.run(['xdotool', *map(str, args)], check=True, capture_output=True, text=True).stdout.strip()
        try:
            def lookup():
                result = subprocess.run(['xdotool', 'search', '--name', '^Xetal pin widget test$'], capture_output=True, text=True)
                return result.stdout.strip()
            window = wait_for(lookup, 'widget did not open')
            time.sleep(.7)
            # Buttons are 50px wide with 2px gaps. Drag A past C's midpoint.
            def drag(start, end, cancel=False):
                xdo('mousemove', '--window', window, start, 28)
                xdo('mousedown', 1); time.sleep(.12)
                for x in range(start, end, 5 if end > start else -5):
                    xdo('mousemove', '--window', window, x, 28); time.sleep(.015)
                xdo('mousemove', '--window', window, end, 28); time.sleep(.18)
                if cancel: xdo('key', 'Escape')
                xdo('mouseup', 1)
            order = lambda: json.loads(state.read_text())['pins']
            drag(24, 146)
            wait_for(lambda: order() == ['b', 'c', 'a'], 'forward drag did not persist: '+str(order()))
            time.sleep(.4)
            drag(128, 5)
            wait_for(lambda: order() == ['a', 'b', 'c'], 'backward drag did not persist: '+str(order()))
            time.sleep(.4)
            drag(24, 146, cancel=True); time.sleep(.3)
            assert order() == ['a', 'b', 'c'], 'cancelled drag changed pins'
            actions = path/'actions.log'
            assert not actions.exists(), 'dragging accidentally launched an app'
            xdo('mousemove', '--window', window, 24, 28); xdo('click', 1)
            wait_for(actions.exists, 'click did not launch')
            assert actions.read_text() == 'launch a\n', actions.read_text()
            # A right-click opens options without another launch; Escape dismisses.
            xdo('click', 3); time.sleep(.25); xdo('key', 'Escape'); time.sleep(.2)
            assert actions.read_text() == 'launch a\n'
            # The directory watcher must replace the widgets after an atomic save.
            replacement = path/'replacement'
            replacement.write_text(json.dumps({'version': 1, 'pins': ['c', 'a', 'b']}))
            replacement.replace(state); time.sleep(.5)
            xdo('mousemove', '--window', window, 24, 28); xdo('click', 1)
            wait_for(lambda: 'launch c\n' in actions.read_text(), 'atomic state update did not refresh icons')
            print('PASS: native drag forward/back, cancel, no accidental launch, click, context menu, live refresh')
        finally:
            proc.terminate(); proc.wait(timeout=5)
            log.seek(0); messages = log.read(); log.close()
            if messages: print(messages)
            assert 'CRITICAL' not in messages and 'ERROR' not in messages, messages


if __name__ == '__main__': run()
