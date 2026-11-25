#!/usr/bin/env python3
"""Check Kitty Ctrl+R and A-key delivery after Wayland focus changes.

Uses the shipped shell configuration in a temporary HOME and a disposable
Hyprland session. All virtual input goes to that session, never the desktop.
Requires a running Hyprland parent, kitty/kitten, PyQt6, wayland-scanner and cc.
Optional --cube-plugin and --minimize-plugin paths exercise desktop effects.
This is a virtual-keyboard test; it cannot exclude physical-device/IME faults.
"""
import argparse,json,os,select,shutil,subprocess,tempfile,time,sys
from pathlib import Path

def main():
    repo=Path(__file__).resolve().parents[1];src=repo/'config/hypr'
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--cube-plugin',type=Path);parser.add_argument('--minimize-plugin',type=Path);args=parser.parse_args()
    root=Path(tempfile.mkdtemp(prefix='fusion-history-check-'));home=root/'home';home.mkdir();runtime=Path(tempfile.mkdtemp(prefix='hk-'));runtime.chmod(0o700);(root/'run').symlink_to(runtime)
    profile=home/'.config/hypr';fetch=profile/'terminal_fetch';fetch.mkdir(parents=True)
    for name in ('bashrc','bash-enhancements.sh','blerc','preferences.py','preferences.json','commands.sh','kitty-settings.conf'):shutil.copy2(src/'terminal_fetch'/name,fetch/name)
    (fetch/'vendor').symlink_to(src/'terminal_fetch/vendor',target_is_directory=True);(fetch/'model.py').write_text('')
    (profile/'scripts').mkdir();shutil.copy2(src/'scripts/terminal-shell.sh',profile/'scripts/terminal-shell.sh');(profile/'theme').mkdir();shutil.copy2(src/'theme/kitty-colors.conf',profile/'theme/kitty-colors.conf')
    (profile/'kitty.conf').write_text((src/'kitty.conf').read_text().replace('@HYPR@',str(profile)));(home/'.bashrc').write_text("PS1='HF_KITTY> '\n")
    instances=json.loads(subprocess.check_output(['hyprctl','-j','instances']));assert instances,'A parent Wayland compositor is required';parent=instances[-1]
    env=dict(os.environ,HOME=str(home),XDG_CONFIG_HOME=str(home/'.config'),XDG_STATE_HOME=str(home/'state'),XDG_CACHE_HOME=str(home/'cache'),XDG_RUNTIME_DIR=str(runtime),WAYLAND_DISPLAY=str(Path('/run/user')/str(os.getuid())/parent['wl_socket']),AQ_BACKENDS='wayland',HYPRLAND_NO_SD_VARS='1',HYPRLAND_NO_SD_NOTIFY='1',QT_QPA_PLATFORM='wayland',QT_QPA_PLATFORMTHEME='',GSETTINGS_BACKEND='memory',LIBGL_ALWAYS_SOFTWARE='1')
    for key in ('DISPLAY','DBUS_SESSION_BUS_ADDRESS','HYPRLAND_INSTANCE_SIGNATURE','KITTY_LISTEN_ON','KITTY_PID','KITTY_WINDOW_ID','KITTY_SHELL_INTEGRATION','KITTY_BASH_INJECT'):env.pop(key,None)
    config=root/'hyprland.lua';config.write_text('hl.monitor({output="",mode="1200x800@60",position="auto",scale=1})\nhl.config({animations={enabled=false},misc={disable_hyprland_logo=true,disable_splash_rendering=true},input={follow_mouse=0}})\n')
    for name,xml in [('pointer',repo/'tests/minimize/wlr-virtual-pointer-unstable-v1.xml'),('keyboard',repo/'tests/native/virtual-keyboard-unstable-v1.xml')]:
     for mode,ext in [('client-header','h'),('private-code','c')]:subprocess.run(['wayland-scanner',mode,str(xml),str(root/f'virtual-{name}.{ext}')],check=True)
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','wayland-client','xkbcommon'],text=True).split()
    subprocess.run(['cc','-I'+str(root),str(repo/'tests/native/gesture-input.c'),str(root/'virtual-pointer.c'),str(root/'virtual-keyboard.c'),'-o',str(root/'input'),*flags],check=True)
    probe=root/'probe.py';probe.write_text('''from PyQt6.QtWidgets import QApplication,QLineEdit\nfrom pathlib import Path\nimport sys\na=QApplication([]);w=QLineEdit();w.setWindowTitle("History focus probe");w.textChanged.connect(lambda text:Path(sys.argv[1]).write_text(text));w.resize(400,200);w.show();a.exec()\n''')
    sys.path.insert(0,str(src))
    from effects.cube import model as cube_model
    from effects.minimize import model as minimize_model
    from cursors import model as cursor_model
    cube_cfg=root/'cube.json';cube_cfg.write_text(cube_model.encode(dict(cube_model.DEFAULTS,top_image='',bottom_image='',sky_image='',sky_mode='gradient')))
    mini_cfg=root/'minimize.conf';mini_cfg.write_text(minimize_model.encode(dict(minimize_model.DEFAULTS)))
    cursor_cfg=profile/'cursors/settings.json';cursor_cfg.parent.mkdir();cursor_cfg.write_bytes(cursor_model.encode(dict(cursor_model.DEFAULTS)))
    env.update(XETAL_CUBE_CONFIG=str(cube_cfg),XETAL_MINIMIZE_CONFIG=str(mini_cfg),XETAL_CURSOR_CONFIG=str(cursor_cfg))
    children=[];log=(root/'session.log').open('w');sock=root/'kitty.sock';ctlbin=str(src/'compat/bin/hyprctl')
    def spawn(args,**kw):
     kw.setdefault('stdout',log);kw.setdefault('stderr',log);c=subprocess.Popen(args,env=env,**kw);children.append(c);return c
    def run(args):
     r=subprocess.run(args,env=env,capture_output=True,text=True,timeout=5);assert r.returncode==0,(args,r.stdout,r.stderr);return r.stdout
    def ctl(*args):return run([ctlbin,*args]).strip()
    def wait(fn,label):
     end=time.monotonic()+12
     while time.monotonic()<end:
      value=fn()
      if value:return value
      time.sleep(.05)
     raise AssertionError(label)
    def remote(*args):return run(['kitten','@','--to','unix:'+str(sock),*args])
    def clients():return json.loads(ctl('-j','clients'))
    def focus(pid):
     c=next(c for c in clients() if c['pid']==pid);ctl('dispatch','focuswindow','address:'+c['address']);time.sleep(.1)
    def key(code,state):
     inputp.stdin.write(f'key {code} {state}\n');inputp.stdin.flush();assert select.select([inputp.stdout],[],[],4)[0];assert inputp.stdout.readline().strip()=='ok';time.sleep(.03)
    def tap(code):key(code,1);key(code,0)
    try:
     comp=spawn(['Hyprland','-c',str(config)],start_new_session=True)
     ipc=wait(lambda:next(iter(runtime.glob('hypr/*/.socket.sock')),None),'IPC');display=wait(lambda:next((p for p in runtime.glob('wayland-*') if p.is_socket()),None),'display');env.update(HYPRLAND_INSTANCE_SIGNATURE=ipc.parent.name,WAYLAND_DISPLAY=str(display))
     ctl('output','create','headless','KEYS')
     for m in json.loads(ctl('-j','monitors')):
      if m['name']!='KEYS':ctl('output','remove',m['name'])
     ctl('dispatch','focusmonitor','KEYS')
     for binary in (args.cube_plugin,args.minimize_plugin):
      if binary is not None:assert ctl('plugin','load',str(binary.resolve(strict=True)))=='ok'
     kitty=spawn(['kitty','--config',str(profile/'kitty.conf'),'--override','allow_remote_control=yes','--override','linux_display_server=wayland','--listen-on','unix:'+str(sock)])
     wait(lambda:sock.exists(),'Kitty');wait(lambda:'HF_KITTY>' in remote('get-text'),'prompt')
     remote('send-text','echo alpha-history-marker\r');time.sleep(.4)
     app=spawn(['/usr/bin/python3',str(probe),str(root/'text')]);wait(lambda:any(c['pid']==app.pid for c in clients()),'text app')
     inputp=spawn([str(root/'input'),'1200','800'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
     for ending in ('search-active','escape','ctrl-c','ctrl-held-at-focus'):
      focus(kitty.pid);key(29,1);tap(19);key(29,0);tap(30);time.sleep(.15)
      screen=remote('get-text');(root/(ending+'.txt')).write_text(screen)
      assert "`a'" in screen and 'alpha-history-marker' in screen,'Ctrl+R history search did not open'
      if ending=='escape':tap(1)
      elif ending=='ctrl-c':key(29,1);tap(46);key(29,0)
      elif ending=='ctrl-held-at-focus':key(29,1)
      focus(app.pid)
      if ending=='ctrl-held-at-focus':key(29,0)
      for k in (30,48,46,30):tap(k)
      expected='abca'*(('search-active','escape','ctrl-c','ctrl-held-at-focus').index(ending)+1)
      wait(lambda:(root/'text').exists() and (root/'text').read_text()==expected,'A works in second app '+ending)
      print('PASS',ending,flush=True)
      focus(kitty.pid);key(29,1);tap(46);key(29,0)
     print('RESULT',root,flush=True)
    finally:
     for c in reversed(children):
      if c.poll() is None:c.terminate()
     for c in children:
      try:c.wait(timeout=4)
      except subprocess.TimeoutExpired:c.kill();c.wait()
     log.close()
     print('Artifacts',root,flush=True)

if __name__=='__main__':main()
