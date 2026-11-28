#!/usr/bin/env python3
"""Native browser fullscreen round-trips in KDE mode, with private profiles/input.

Usage: check-fullscreen-restore.py MEMORY_SO MINIMIZE_SO CONTROLS_SO OUTPUT_DIR
       [--browser brave|chrome|firefox] [--expect-bug]
The fixture uses an offline HTML fullscreen surface, the real native title bar,
and a separate compositor. It never changes the parent session's windows.
"""
from pathlib import Path
import argparse, json, os, shlex, shutil, subprocess, sys, tempfile, time
repo=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('memory',type=Path);parser.add_argument('minimize',type=Path);parser.add_argument('controls',type=Path)
parser.add_argument('output',type=Path);parser.add_argument('--browser',choices=('brave','chrome','firefox'),default='brave')
parser.add_argument('--expect-bug',action='store_true')
args=parser.parse_args()
plugins=[p.resolve(strict=True) for p in (args.minimize,args.memory,args.controls)]
root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
sys.path[:0]=[str(repo/'tests'),str(repo/'config/hypr/compat')]
from nested_session import nested_environment, assert_seat_isolated
import hypr_compat
sys.path.insert(0,str(repo/'config/hypr'))
from effects.minimize import model as minimize_model
from effects.window_close import model as controls_model
runtime=Path(tempfile.mkdtemp(prefix='fr-'));(root/'runtime').symlink_to(runtime,target_is_directory=True)
home=root/'home';home.mkdir();profile=home/'.config/hypr';(profile/'workspaces').mkdir(parents=True)
for component,model in [('minimize',minimize_model),('window_close',controls_model)]:
 target=profile/'effects'/component/'settings.conf';target.parent.mkdir(parents=True);target.write_text(model.encode(model.DEFAULTS))
(profile/'workspaces/rules.json').write_text('{"version":1,"default_layout":"kde","workspaces":{}}')
parent=os.environ['WAYLAND_DISPLAY'];parent=parent if parent.startswith('/') else str(Path(os.environ['XDG_RUNTIME_DIR'])/parent)
env=nested_environment(dict(os.environ,HOME=str(home),XDG_RUNTIME_DIR=str(runtime),WAYLAND_DISPLAY=parent,XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'),XDG_DATA_HOME=str(home/'.local/share'),XDG_STATE_HOME=str(home/'.local/state'),MOZ_ENABLE_WAYLAND='1',XDG_SESSION_TYPE='wayland',XDG_CURRENT_DESKTOP='Hyprland',GSETTINGS_BACKEND='memory',DBUS_SYSTEM_BUS_ADDRESS='unix:path='+str(runtime/'no-system-bus')))
for key in ('HYPRLAND_INSTANCE_SIGNATURE','DISPLAY','DBUS_SESSION_BUS_ADDRESS'):env.pop(key,None)
for name,xml in [('pointer',repo/'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'),('keyboard',repo/'tests/native/virtual-keyboard-unstable-v1.xml')]:
 for mode,suffix in [('client-header','h'),('private-code','c')]:subprocess.run(['wayland-scanner',mode,str(xml),str(root/f'virtual-{name}.{suffix}')],check=True)
flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client','xkbcommon'],text=True))
subprocess.run(['cc','-I'+str(root),str(repo/'tests/native/gesture-input.c'),str(root/'virtual-pointer.c'),str(root/'virtual-keyboard.c'),'-o',str(root/'input'),*flags],check=True)
conf=root/'hyprland.conf';conf.write_text('monitor=,1280x900@60,auto,1\nmisc:disable_hyprland_logo=true\nmisc:disable_splash_rendering=true\nmisc:disable_hyprland_guiutils_check=true\nanimations:enabled=false\ninput:follow_mouse=0\nxwayland:enabled=false\n')
lua=conf.with_suffix('.lua');lua.write_text(hypr_compat.Renderer(profile).render(conf))
processes=[];logs=[];reports=[]
def spawn(args,**kw):
 log=(root/f'process-{len(processes)}.log').open('w');logs.append(log);p=subprocess.Popen(args,env=env,stdout=log,stderr=log,**kw);processes.append(p);return p
def ctl(*args):
 p=subprocess.run(['/usr/bin/hyprctl',*args],env=env,text=True,capture_output=True,timeout=8);assert p.returncode==0,p.stdout+p.stderr;return p.stdout.strip()
def dispatch(cmd,arg=''): assert ctl('dispatch',hypr_compat.dispatcher(cmd,arg))=='ok'
def wait(fn,label):
 end=time.monotonic()+15
 while time.monotonic()<end:
  result=fn()
  if result:return result
  time.sleep(.06)
 raise AssertionError(label)
compositor=spawn(['Hyprland','--config',str(lua)],start_new_session=True)
try:
 endpoint=wait(lambda:next(iter(runtime.glob('hypr/*/.socket.sock')),None),'compositor socket');env['HYPRLAND_INSTANCE_SIGNATURE']=endpoint.parent.name
 env['WAYLAND_DISPLAY']=str(wait(lambda:next((p for p in runtime.glob('wayland-*') if p.is_socket()),None),'Wayland socket'))
 assert_seat_isolated(compositor.pid,root/'process-0.log')
 assert ctl('output','create','headless','RESTORE')=='ok'
 for m in json.loads(ctl('-j','monitors')):
  if m['name']!='RESTORE':assert ctl('output','remove',m['name'])=='ok'
 assert ctl('eval',hypr_compat.call('monitor',{'output':'RESTORE','mode':'1280x900@60','position':'0x0','scale':1}))=='ok'
 dispatch('focusmonitor','RESTORE')
 for group in ('mice','keyboards'):
  for dev in json.loads(ctl('-j','devices'))[group]:assert ctl('eval',hypr_compat.call('device',{'name':dev['name'],'enabled':False}))=='ok'
 for plugin in plugins: assert ctl('plugin','load',str(plugin))=='ok'
 blog=(root/'dbus.log').open('w');logs.append(blog);bus=subprocess.Popen(['dbus-daemon','--session','--nofork','--print-address=1'],env=env,stdout=subprocess.PIPE,stderr=blog,text=True);processes.append(bus);env['DBUS_SESSION_BUS_ADDRESS']=bus.stdout.readline().strip()
 inp=subprocess.Popen([str(root/'input'),'1280','900'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);processes.append(inp)
 def gesture(cmd):
  inp.stdin.write(cmd+'\n');inp.stdin.flush();assert inp.stdout.readline().strip()=='ok';time.sleep(.08)
 def key(code):gesture(f'key {code} 1');gesture(f'key {code} 0')
 page=root/'fullscreen.html';page.write_text('<!doctype html><title>Fullscreen ready</title><style>html,body{margin:0;height:100%;background:#15334a;color:white;font:24px sans-serif}body{display:grid;place-items:center}</style><body>Press F to enter fullscreen<script>addEventListener("keydown",e=>{if(e.key=="f")document.documentElement.requestFullscreen()});addEventListener("fullscreenchange",()=>document.title=document.fullscreenElement?"Fullscreen on":"Fullscreen off");</script>')
 firefox=root/'firefox';firefox.mkdir();(firefox/'user.js').write_text('user_pref("browser.shell.checkDefaultBrowser",false);\nuser_pref("browser.aboutwelcome.enabled",false);\nuser_pref("browser.startup.homepage_override.mstone","ignore");\nuser_pref("browser.newtabpage.enabled",false);\nuser_pref("datareporting.policy.dataSubmissionEnabled",false);\nuser_pref("toolkit.telemetry.enabled",false);\nuser_pref("full-screen-api.warning.timeout",0);\n')
 browser={'brave':shutil.which('brave') or '/opt/brave-bin/brave',
          'chrome':shutil.which('google-chrome-stable') or '/opt/google/chrome/chrome',
          'firefox':shutil.which('firefox')}[args.browser]
 if args.browser=='firefox': command=[browser,'--no-remote','--profile',str(firefox),str(page)]
 else: command=[browser,'--ozone-platform=wayland','--user-data-dir='+str(firefox),'--no-first-run',
                '--no-default-browser-check','--disable-background-networking','--disable-sync','--password-store=basic',
                '--disable-features=Translate',str(page)]
 app=spawn(command)
 def current():return next((c for c in json.loads(ctl('-j','clients')) if c['pid']==app.pid),None)
 w=wait(current,args.browser);address=w['address'];dispatch('focuswindow','address:'+address);time.sleep(1)
 ids=json.loads(ctl('xetal-windowbuttons'))['windows']
 window_id=next(i for i in ids if json.loads(ctl('xetal-windowbuttons',i))['address']==address)
 dispatch('setfloating','address:'+address);dispatch('resizewindowpixel','exact 820 580,address:'+address);dispatch('movewindowpixel','exact 200 120,address:'+address);time.sleep(.3)
 gesture('move 640 430');gesture('button 1');gesture('button 0')
 for mode in (0,1):
  for kind in ('html','f11'):
   for cycle in range(2):
    assert ctl('xetal-window-state',address,str(mode),str(mode))=='ok';time.sleep(.4);before=current()
    key(33 if kind=='html' else 87);wait(lambda:current()['fullscreen']==2,'enter '+kind+' fullscreen');time.sleep(.25);full=current()
    key(1 if kind=='html' else 87);wait(lambda:current()['fullscreen']!=2,'exit '+kind+' fullscreen');time.sleep(.4);after=current()
    record=dict(browser=args.browser,kind=kind,cycle=cycle,mode=mode,before=before,fullscreen=full,after=after);reports.append(record)
    print(args.browser,kind,'cycle',cycle+1,'mode',mode,'restored',after['fullscreen'],flush=True)
    if args.expect_bug:
     if mode==1 and after['fullscreen']==0:
      print('PASS: reproduced loss of maximization with the previous adapter',flush=True)
      (root/'report.json').write_text(json.dumps(reports,indent=2)+'\n')
      raise SystemExit(0)
    else:
     assert after['fullscreen']==mode and after['fullscreenClient']==mode,record
     assert (after['at'],after['size'])==(before['at'],before['size']),record
     assert after['monitor']==before['monitor'] and after['workspace']==before['workspace'],record
     assert after['floating']==before['floating'],record
    # The real KDE restore action remains an explicit request for normal size.
    if mode:
     bar=json.loads(ctl('xetal-windowbuttons',window_id))['titlebar'];assert bar['enabled']
     x,y,width,height=bar['buttons'][2]
     gesture(f'move {round(x+width/2)} {round(y+height/2)}');gesture('button 1');gesture('button 0')
     wait(lambda:current()['fullscreen']==0,'explicit restore after fullscreen')
 if args.expect_bug: raise AssertionError('The old adapter did not reproduce the regression')
 (root/'report.json').write_text(json.dumps(reports,indent=2)+'\n');print('Evidence:',root,flush=True)
finally:
 for p in reversed(processes):
  if p.poll() is None:p.terminate()
 for p in reversed(processes):
  try:p.wait(timeout=3)
  except subprocess.TimeoutExpired:p.kill();p.wait()
 for log in logs:log.close()
