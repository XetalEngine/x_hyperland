#!/usr/bin/env python3
"""Real video playback and authenticated VNC/RDP on a private nested compositor.
No host display, firewall, power setting, or phone is changed.
"""
import argparse,json,os,shutil,socket,ssl,struct,subprocess,sys,tempfile,time
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
    folder=args.output;folder.mkdir(parents=True,exist_ok=False)
    parent=json.loads(subprocess.check_output(['hyprctl','-j','instances']))[-1]
    runtime=Path(tempfile.mkdtemp(prefix='fusion-check-'));runtime.chmod(0o700)
    home=folder/'home';home.mkdir()
    env=dict(os.environ,HOME=str(home),XDG_CONFIG_HOME=str(home/'.config'),XDG_STATE_HOME=str(home/'.local/state'),XDG_RUNTIME_DIR=str(runtime),WAYLAND_DISPLAY=str(Path(os.environ['XDG_RUNTIME_DIR'])/parent['wl_socket']),AQ_BACKENDS='wayland',HYPRLAND_NO_SD_VARS='1',HYPRLAND_NO_SD_NOTIFY='1',QT_QPA_PLATFORM='wayland',PYTHONPATH=str(ROOT/'config/hypr'))
    for key in ('DISPLAY','DBUS_SESSION_BUS_ADDRESS','HYPRLAND_INSTANCE_SIGNATURE'):env.pop(key,None)
    config=folder/'hyprland.lua';config.write_text('hl.monitor({output="",mode="1280x720@60",position="auto",scale=1})\nhl.config({animations={enabled=false},misc={disable_hyprland_logo=true,disable_splash_rendering=true}})\n')
    children=[]
    def spawn(argv,**kwargs):
        child=subprocess.Popen(argv,env=env,**kwargs);children.append(child);return child
    def run(argv,timeout=30):
        result=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=timeout)
        if result.returncode:raise RuntimeError(str(argv)+': '+(result.stdout+result.stderr)[-3000:])
        return result.stdout
    try:
        with (folder/'compositor.log').open('w') as log:
            compositor=spawn(['Hyprland','-c',str(config)],stdout=log,stderr=log,start_new_session=True)
        for _ in range(100):
            assert compositor.poll() is None,(folder/'compositor.log').read_text()[-1500:]
            try:instances=json.loads(run(['hyprctl','-j','instances']))
            except (ValueError,RuntimeError):time.sleep(.1);continue
            instance=next((i for i in instances if i['pid']==compositor.pid),None)
            if instance:
                env.update(HYPRLAND_INSTANCE_SIGNATURE=instance['instance'],WAYLAND_DISPLAY=instance['wl_socket']);break
            time.sleep(.1)
        time.sleep(1)
        old=json.loads(run(['hyprctl','-j','monitors']))
        output=old[0]['name'] if os.environ.get('FUSION_CAPTURE_CHECK')=='1' else 'FUSION-CHECK'
        if output=='FUSION-CHECK':
            run(['hyprctl','output','create','headless',output])
            for monitor in old:run(['hyprctl','output','remove',monitor['name']])
        env['FUSION_TEST_OUTPUT']=output
        run([str(ROOT/'config/hypr/compat/bin/hyprctl'),'keyword','monitor',output+',1280x720@60,0x0,1'])
        run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=640x360:r=15','-t','2','-c:v','libx264','-pix_fmt','yuv420p',str(folder/'blue.mp4')])
        Image.new('RGB',(1280,720),'red').save(folder/'red.png')
        paper=folder/'hyprpaper.conf';paper.write_text(f'ipc = true\nsplash = false\nwallpaper {{\n monitor =\n path = {folder/"red.png"}\n fit_mode = cover\n}}\n')
        with (folder/'hyprpaper.log').open('w') as log:spawn(['hyprpaper','-c',str(paper)],stdout=log,stderr=log)
        time.sleep(1)
        # Nested NVIDIA screencopy can stall independently of the working
        # parent compositor. Inspect one pixel in our own nested window instead.
        if os.environ.get('FUSION_CAPTURE_CHECK')=='1':
            with (folder/'worker.log').open('w') as log:
                worker_process=spawn([sys.executable,str(Path(__file__).resolve()),str(folder),'--worker'],stdout=log,stderr=log)
            for _ in range(100):
                if (folder/'video-ready').exists():break
                if worker_process.poll() is not None:raise RuntimeError((folder/'worker.log').read_text())
                time.sleep(.1)
            parent_env=dict(os.environ,HYPRLAND_INSTANCE_SIGNATURE=parent['instance'],WAYLAND_DISPLAY=parent['wl_socket'])
            clients=json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','clients'],env=parent_env))
            client=next(c for c in clients if c['pid']==compositor.pid)
            # Only our private test window is raised; restore prior focus below.
            active=json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','activewindow'],env=parent_env))
            subprocess.run([str(ROOT/'config/hypr/compat/bin/hyprctl'),'dispatch','focuswindow','address:'+client['address']],env=parent_env,check=True,capture_output=True)
            time.sleep(1)
            x,y=client['at'];width,height=client['size']
            shot=folder/'video-pixel.png'
            subprocess.run(['grim','-g',f'{int(x+width/2)},{int(y+height/2)} 1x1',str(shot)],env=parent_env,check=True,timeout=8)
            pixel=Image.open(shot).convert('RGB').getpixel((0,0))
            if active.get('address'):subprocess.run([str(ROOT/'config/hypr/compat/bin/hyprctl'),'dispatch','focuswindow','address:'+active['address']],env=parent_env,capture_output=True)
            assert pixel[2]>170 and pixel[0]<70,pixel
            (folder/'pixel-check-done').touch()
            worker_process.wait(timeout=90)
            if worker_process.returncode:raise RuntimeError((folder/'worker.log').read_text())
        else:run([sys.executable,str(Path(__file__).resolve()),str(folder),'--worker'],timeout=120)
        print('PASS: video decoder/IPC, VNC authentication, RDP authentication, private process shutdown.')
    finally:
        for child in reversed(children):
            if child.poll() is None:child.terminate()
        for child in children:
            try:child.wait(timeout=8)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        shutil.rmtree(runtime,ignore_errors=True)


def worker(folder):
    output=os.environ['FUSION_TEST_OUTPUT']
    sys.path.insert(0,str(ROOT/'config/hypr'))
    from desktop_services import remote
    from wallpaper import video
    def read(connection,count):
        data=b''
        while len(data)<count:
            chunk=connection.recv(count-len(data))
            if not chunk:raise RuntimeError('Remote peer disconnected.')
            data+=chunk
        return data
    def vnc(password):
        with socket.create_connection(('127.0.0.1',5999),timeout=5) as raw:
            assert read(raw,12).startswith(b'RFB 003.008');raw.sendall(b'RFB 003.008\n')
            kinds=read(raw,read(raw,1)[0]);assert 1 not in kinds,kinds;assert 19 in kinds,kinds;raw.sendall(bytes([19]))
            version=read(raw,2);raw.sendall(version);assert read(raw,1)==b'\0'
            types=[struct.unpack('>I',read(raw,4))[0] for _ in range(read(raw,1)[0])]
            assert 262 in types,types;raw.sendall(struct.pack('>I',262));assert read(raw,1)==b'\1'
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.check_hostname=False;context.verify_mode=ssl.CERT_NONE
            with context.wrap_socket(raw,server_hostname='localhost') as tls:
                username=b'fusion';password=password.encode();tls.sendall(struct.pack('>II',len(username),len(password))+username+password)
                status=struct.unpack('>I',read(tls,4))[0]
                if status==0:
                    tls.sendall(b'\1');header=read(tls,24);width,height=struct.unpack('>HH',header[:4]);assert width>0 and height>0
                return status
    directory=folder/'remote';player=None
    try:
        player=video.launch(output,folder/'blue.mp4');time.sleep(2)
        if os.environ.get('FUSION_CAPTURE_CHECK')=='1':
            (folder/'video-ready').touch()
            for _ in range(150):
                if (folder/'pixel-check-done').exists():break
                time.sleep(.1)
            else:raise RuntimeError('The parent pixel check did not finish.')
        video.stop_record(player);player=None
        remote.save({**remote.DEFAULTS,'output':output,'username':'fusion','port':5999},'fusion-private-test-password',directory)
        remote.start(directory)
        assert vnc('wrong-private-password')!=0
        assert vnc('fusion-private-test-password')==0
        remote.stop(directory);assert not remote.process(directory)
        remote.save({**remote.DEFAULTS,'protocol':'rdp','output':output,'username':'fusion','port':33999,'control':True},directory=directory)
        remote.start(directory)
        for password,good in [('wrong-private-password',False),('fusion-private-test-password',True)]:
            result=subprocess.run(['wlfreerdp3','/v:127.0.0.1:33999','/u:fusion','/p:'+password,'/cert:ignore','+auth-only','/auth-pkg-list:none,ntlm','/log-level:DEBUG'],capture_output=True,text=True,timeout=25)
            (folder/('rdp-good.log' if good else 'rdp-rejected.log')).write_text(result.stdout+result.stderr)
            # FreeRDP's Wayland client exits 255 even after a successful
            # auth-only handshake; the core reports the authentication result.
            log=result.stdout+result.stderr
            success='Authentication only, exit status 1' in log
            assert success==good,(result.returncode,log[-2000:])
        remote.stop(directory);assert not remote.process(directory)
    finally:
        if player:video.stop_record(player)
        remote.stop(directory)


if __name__=='__main__':
    if '--worker' in sys.argv:worker(Path(sys.argv[1]))
    else:main()
