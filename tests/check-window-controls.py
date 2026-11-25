#!/usr/bin/env python3
"""Map the real controls editor against stale geometry in an isolated Hyprland."""
import sys,json,subprocess,tempfile,os,time,shutil,hashlib
from pathlib import Path
repo=Path(__file__).resolve().parents[1];src=repo/'config/hypr'
sys.path.insert(0,str(src));from compat.hypr_compat import window_rule,call
root=Path(tempfile.mkdtemp(prefix='fusion-controls-check-'));home=root/'home';home.mkdir();runtime=Path(tempfile.mkdtemp(prefix='wc-'));runtime.chmod(0o700);profile=home/'.config/hypr'
for directory,dirs,files in os.walk(src):
 dirs[:]=[d for d in dirs if not d.startswith('.') and d not in ('__pycache__','vendor','third_party','packs','wallpapers','assets','qt5','qt6','gtk3')]
 for name in files:
  p=Path(directory)/name
  if p.suffix in ('.py','.json','.conf','.colors','.css'):
   out=profile/p.relative_to(src);out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
parent=json.loads(subprocess.check_output(['hyprctl','-j','instances']))[0]
env=dict(os.environ,HOME=str(home),XDG_CONFIG_HOME=str(home/'.config'),XDG_STATE_HOME=str(home/'state'),XDG_CACHE_HOME=str(home/'cache'),XDG_DATA_HOME=str(home/'data'),XDG_RUNTIME_DIR=str(runtime),WAYLAND_DISPLAY=str(Path(os.environ['XDG_RUNTIME_DIR'])/parent['wl_socket']),AQ_BACKENDS='wayland',HYPRLAND_NO_SD_VARS='1',HYPRLAND_NO_SD_NOTIFY='1',QT_QPA_PLATFORM='wayland',QT_QPA_PLATFORMTHEME='',QT_PLUGIN_PATH='',QT_WAYLAND_DISABLE_WINDOWDECORATION='1',LIBGL_ALWAYS_SOFTWARE='1')
for k in ('HYPRLAND_INSTANCE_SIGNATURE','DISPLAY','DBUS_SESSION_BUS_ADDRESS'):env.pop(k,None)
config=root/'hyprland.lua';config.write_text('hl.monitor({output="",mode="1280x1000@60",position="auto",scale=1})\nhl.config({animations={enabled=false},misc={disable_hyprland_logo=true,disable_splash_rendering=true},input={follow_mouse=0}})\n')
children=[];log=(root/'session.log').open('w');ctlbin=src/'compat/bin/hyprctl'
def spawn(args):
 p=subprocess.Popen(args,env=env,stdout=log,stderr=log);children.append(p);return p
def ctl(*args):return subprocess.check_output([str(ctlbin),*args],env=env,text=True,timeout=5).strip()
def wait(fn):
 end=time.monotonic()+15
 while time.monotonic()<end:
  v=fn()
  if v:return v
  time.sleep(.06)
 raise RuntimeError('Timed out; '+str(root))
def clients():return json.loads(ctl('-j','clients'))
def open_dialog():
 p=spawn(['/usr/bin/python3',str(profile/'effects/window_close/window_settings.py'),'--workspace','1'])
 c=wait(lambda:next((c for c in clients() if c['pid']==p.pid),None));time.sleep(.3)
 return p,next(c for c in clients() if c['pid']==p.pid)
try:
 spawn(['/usr/bin/Hyprland','-c',str(config)]);ipc=wait(lambda:next(iter(runtime.glob('hypr/*/.socket.sock')),None));display=wait(lambda:next((p for p in runtime.glob('wayland-*') if p.is_socket()),None));env.update(HYPRLAND_INSTANCE_SIGNATURE=ipc.parent.name,WAYLAND_DISPLAY=str(display))
 ctl('output','create','headless','TEST')
 for m in json.loads(ctl('-j','monitors')):
  if m['name']!='TEST':ctl('output','remove',m['name'])
 binary=subprocess.check_output(['/usr/bin/python3',str(src/'runtime/window_memory/build.py')],text=True).strip();assert ctl('plugin','load',binary)=='ok'
 p,c=open_dialog();meta=json.loads(ctl('xetal-windows'))[c['address']]
 print('Baseline:',{k:c[k] for k in ('class','floating','fullscreen','size')},flush=True)
 app=c.get('initialClass') or c['class'];key=hashlib.sha256((app.casefold()+':'+('dialog:' if meta['dialog'] else 'window:')+meta['role']).encode()).hexdigest()[:32]
 p.terminate();p.wait();wait(lambda:not clients())
 saved=dict(floating=False,fullscreen=0,client_fullscreen=0,size=[1280,1000],area=[1280,1000],mode_saved=True)
 state=root/'memory.json';state.write_text(json.dumps(dict(version=1,windows={key:saved})));assert ctl('xetal-memory-source',str(state))=='ok'
 # Read the shipped rule, so the test covers actual configuration translation.
 text=(src/'hyprland.conf').read_text();block=text.split('name = fusion-window-controls',1)[1].split('}',1)[0]
 fields=[('name','fusion-window-controls')]+[tuple(s.strip() for s in line.split('=',1)) for line in block.splitlines() if '=' in line]
 assert ctl('eval',call('window_rule',window_rule(fields)))=='ok'
 for mode in ('tiled','maximized','fullscreen','oversized'):
  saved.update(floating=mode!='tiled',fullscreen={'maximized':1,'fullscreen':2}.get(mode,0),client_fullscreen={'maximized':1,'fullscreen':2}.get(mode,0))
  saved['floating_size']=[1280,1000];state.write_text(json.dumps(dict(version=1,windows={key:saved})))
  p,c=open_dialog();assert c['floating'] and c['fullscreen']==0 and c['size'][0]<1000 and c['size'][1]<1000,c
  before=c['size'];ctl('dispatch','resizewindowpixel','exact 760 870,address:'+c['address']);time.sleep(.2)
  after=next(i for i in clients() if i['pid']==p.pid)['size'];assert after!=before,(before,after)
  print('PASS',mode,'opens',before,'resizes',after,flush=True);p.terminate();p.wait();wait(lambda:not clients())
 print('ARTIFACTS',root,flush=True)
finally:
 for p in reversed(children):
  if p.poll() is None:p.terminate()
 for p in children:
  try:p.wait(timeout=4)
  except subprocess.TimeoutExpired:p.kill();p.wait()
 log.close()
