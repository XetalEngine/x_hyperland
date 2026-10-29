#!/usr/bin/env python3
"""Exercise cube cadence and live thumbnail streams in a disposable compositor.

Usage: check-preview-fps.py CUBE_PLUGIN EMPTY_OUTPUT_DIRECTORY [PREVIOUS_PLUGIN]
All windows and compositor commands belong to the nested test session.
"""
import collections
import json
import os
from pathlib import Path
import select
import struct
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'config/hypr'))
from effects.cube import model

FIXTURE = '''from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPainter,QColor
from PyQt6.QtWidgets import QApplication,QWidget
import json,sys
app=QApplication([]);app.setDesktopFileName('fusion-fps-fixture')
class Moving(QWidget):
 def __init__(self,n):
  super().__init__();self.n=n;self.count=0;self.setWindowTitle('FPS fixture '+str(n));self.resize(450,320)
  self.timer=QTimer(self);self.timer.setInterval(16);self.timer.timeout.connect(self.update);self.timer.start();self.show()
 def paintEvent(self,e):
  self.count+=1;p=QPainter(self);p.fillRect(self.rect(),QColor.fromHsv((self.count*5+self.n*70)%360,170,150));p.setPen(QColor('white'));p.drawText(30,45,'Live frame '+str(self.count))
windows=[Moving(i) for i in range(3)]
timer=QTimer();timer.setInterval(100);timer.timeout.connect(lambda:open(sys.argv[1],'w').write(json.dumps([w.count for w in windows])));timer.start()
app.exec()
'''


def main():
    binary = Path(sys.argv[1]).resolve(strict=True)
    root = Path(sys.argv[2]).resolve(); root.mkdir(parents=True, exist_ok=False)
    values = model.validate(model.DEFAULTS); values.update(duration=0)
    config = root/'settings.json'; config.write_text(model.encode(values))
    (root/'hyprland.conf').write_text('''monitor = ,1280x800@60,auto,1
misc {
    disable_hyprland_logo = true
    disable_splash_rendering = true
}
xwayland {
    enabled = false
}
animations {
    enabled = false
}
''')
    (root/'fixture.py').write_text(FIXTURE)
    env = dict(os.environ); env.pop('HYPRLAND_INSTANCE_SIGNATURE',None)
    env.update(AQ_BACKENDS='wayland',XETAL_CUBE_CONFIG=str(config))
    processes = []
    logs = []
    try:
        logs.append((root/'compositor.log').open('w'))
        compositor = subprocess.Popen(['Hyprland','--config',str(root/'hyprland.conf')],env=env,stdout=logs[-1],stderr=logs[-1],start_new_session=True)
        processes.append(compositor)
        for _ in range(100):
            assert compositor.poll() is None,'Nested compositor exited'
            instances = json.loads(subprocess.check_output(['hyprctl','-j','instances'],text=True))
            instance = next((i for i in instances if i['pid']==compositor.pid),None)
            if instance:
                env.update(HYPRLAND_INSTANCE_SIGNATURE=instance['instance'],WAYLAND_DISPLAY=instance['wl_socket'],QT_QPA_PLATFORM='wayland')
                break
            time.sleep(.1)
        else: raise RuntimeError('No nested compositor instance')
        def run(*args):
            result = subprocess.run(args,env=env,capture_output=True,text=True,timeout=15)
            assert result.returncode==0,(args,result.stdout,result.stderr)
            return result.stdout.strip()
        def dispatch(*args):
            answer=run('hyprctl','dispatch',*args); assert answer=='ok',(args,answer)
        def status(): return json.loads(run('hyprctl','xetal-cube'))
        time.sleep(.4)
        if len(sys.argv)>3:
            legacy=values.copy();legacy.pop('preview_fps');config.write_text(json.dumps(legacy))
            old=str(Path(sys.argv[3]).resolve(strict=True))
            assert run('hyprctl','plugin','load',old)=='ok'
            dispatch('xetalcube:preview');dispatch('xetalcube:finish','cancel');time.sleep(.1)
            assert run('hyprctl','plugin','unload',old)=='ok'
            config.write_text(model.encode(values))
        assert run('hyprctl','plugin','load',str(binary))=='ok'
        logs.append((root/'fixture.log').open('w'))
        fixture=subprocess.Popen(['python3',str(root/'fixture.py'),str(root/'paint-counts.json')],env=env,stdout=logs[-1],stderr=logs[-1]);processes.append(fixture)
        for _ in range(80):
            clients=json.loads(run('hyprctl','-j','clients'))
            if len(clients)==3: break
            time.sleep(.1)
        assert len(clients)==3,clients
        monitor=json.loads(run('hyprctl','-j','monitors'))[0]['name']
        dispatch('movetoworkspacesilent','2,address:'+clients[-1]['address'])
        results=[]
        for fps in (10,60):
            values['preview_fps']=fps;config.write_text(model.encode(values));dispatch('xetalcube:reload');dispatch('xetalcube:preview',monitor)
            time.sleep(.35); before=status(); start=time.monotonic()
            paints_before=json.loads((root/'paint-counts.json').read_text())
            time.sleep(2); after=status(); elapsed=time.monotonic()-start
            assert before['active'] and after['active'], {'before':before,'after':after,'monitors':json.loads(run('hyprctl','-j','monitors'))}
            paints_after=json.loads((root/'paint-counts.json').read_text())
            frames=after['preview_frames']-before['preview_frames'];captures=after['window_captures']-before['window_captures']
            record={'kind':'cube','target':fps,'actual':round(frames/elapsed,1),'captures':captures,'frames':frames,'client_paints':[b-a for a,b in zip(paints_before,paints_after)]}
            print(record,flush=True);results.append(record)
            assert captures==frames*3,record
            assert fps*.72<=frames/elapsed<=fps*1.15,record
            assert not after['error'],after
            assert min(record['client_paints'])>=fps,record
            dispatch('xetalcube:finish','cancel');time.sleep(.1)
        helper=REPO/'config/hypr/share-picker/window-preview'
        # The shared adapter must keep previews live with the Cube effect off.
        values['enabled']=False;config.write_text(model.encode(values));dispatch('xetalcube:reload')
        assert not status()['enabled']
        header=struct.Struct('<4sQIII')
        for fps in (10,60):
            capture=subprocess.Popen([str(helper),'--stream'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE);processes.append(capture)
            capture.stdin.write((str(fps)+' '+' '.join(c['address'] for c in clients)+'\n').encode());capture.stdin.flush()
            buffer=bytearray();counts=collections.Counter();colors=collections.defaultdict(set);start=time.monotonic()
            while time.monotonic()-start<2.5:
                assert capture.poll() is None,capture.stderr.read().decode()
                if not select.select([capture.stdout],[],[],.1)[0]:continue
                block=os.read(capture.stdout.fileno(),1024*1024)
                assert block,'Capture pipe closed';buffer.extend(block)
                consumed=0
                while len(buffer)-consumed>=header.size:
                    magic,address,w,h,length=header.unpack_from(buffer,consumed)
                    assert magic==b'XTPF' and length==w*h*4 and length<=640*400*4
                    end=consumed+header.size+length
                    if end>len(buffer):break
                    counts[f'0x{address:x}']+=1
                    colors[address].add(bytes(buffer[consumed+header.size:consumed+header.size+4]))
                    consumed=end
                if consumed:del buffer[:consumed]
            elapsed=time.monotonic()-start;capture.stdin.close();capture.wait(timeout=3)
            assert capture.returncode==0,capture.stderr.read().decode()
            record={'kind':'switcher','target':fps,'actual':{a:round(n/elapsed,1) for a,n in counts.items()},'unique_frames':{hex(a):len(v) for a,v in colors.items()}}
            print(record,flush=True);results.append(record)
            assert len(counts)==3,record
            assert all(fps*.65<=n/elapsed<=fps*1.15 for n in counts.values()),record
            assert min(map(len,colors.values()))>=fps,record
        time.sleep(2.4)
        assert status()['preview_sources']==0,status()
        paints_before=json.loads((root/'paint-counts.json').read_text())
        time.sleep(.5)
        paints_after=json.loads((root/'paint-counts.json').read_text())
        assert any(b==a for a,b in zip(paints_before,paints_after)), 'Hidden source did not return to sleep'
        picture=subprocess.run([str(helper),clients[0]['address']],env=env,capture_output=True,timeout=4)
        assert picture.returncode==0 and picture.stdout.startswith(b'\x89PNG\r\n\x1a\n'),'One-shot screenshot compatibility'
        assert run('hyprctl','plugin','unload',str(binary))=='ok'
        (root/'results.json').write_text(json.dumps(results,indent=2))
        print('PASS: per-window cube cadence, hidden-workspace client frames, persistent streams at 10/60 FPS, bounded protocol and clean shutdown',flush=True)
    finally:
        for process in reversed(processes):
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=4)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        for log in logs:log.close()


if __name__=='__main__':main()
