"""Per-output video wallpaper playback with a persistent still-image fallback."""
from pathlib import Path
import fcntl
import hashlib
import json
import os
import copy
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from desktop_services.common import STATE,monitors,process_start,read,run,write

EXTENSIONS={'.mp4','.webm','.mkv','.mov','.m4v','.avi'}
SELECTION=ROOT/'state/videos.json'
RUNTIME=STATE/'video-wallpapers'


def binary():
    path=ROOT.parent/'desktop_services/.build/mpvpaper/mpvpaper'
    return str(path) if path.is_file() else shutil.which('mpvpaper')


def inspect(filename):
    path=Path(filename).expanduser().resolve(strict=True)
    if path.suffix.lower() not in EXTENSIONS or not path.is_file():raise ValueError('Choose a local video file.')
    data=json.loads(run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height:format=duration','-of','json',path],timeout=20))
    streams=data.get('streams',[])
    if not streams or not 0<int(streams[0].get('width',0))*int(streams[0].get('height',0))<=100_000_000:
        raise ValueError('This file has no supported video stream.')
    return path,streams[0]


def poster(filename):
    path=Path(filename).resolve(strict=True);stat=path.stat()
    key=hashlib.sha256(f'{path}\0{stat.st_size}\0{stat.st_mtime_ns}'.encode()).hexdigest()[:32]
    folder=ROOT/'state/video-posters';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=folder/(key+'.png')
    if target.is_file():return target
    inspect(path)
    fd,temporary=tempfile.mkstemp(prefix='.poster-',suffix='.png',dir=folder);os.close(fd)
    try:
        run(['ffmpeg','-nostdin','-v','error','-threads','2','-i',path,'-map','0:v:0','-frames:v','1',
             '-vf','scale=1920:1080:force_original_aspect_ratio=decrease','-y',temporary],timeout=30)
        if Path(temporary).stat().st_size==0:raise ValueError('The video could not be previewed.')
        os.replace(temporary,target)
    finally:Path(temporary).unlink(missing_ok=True)
    return target


def selections():
    data=read(SELECTION,dict(version=1,outputs={}))
    if data.get('version')!=1 or not isinstance(data.get('outputs'),dict):raise ValueError('Invalid saved video wallpapers.')
    return data


def alive(record):
    if not record or process_start(record.get('pid',0))!=record.get('start'):return False
    try:
        args=Path(f'/proc/{record["pid"]}/cmdline').read_bytes().split(b'\0')
        return Path(args[0].decode()).name=='mpvpaper' and record['path'].encode() in args
    except (OSError,KeyError,ValueError):return False


def stop_record(record):
    if alive(record):
        try:
            os.kill(record['pid'],signal.SIGCONT);os.kill(record['pid'],signal.SIGTERM)
        except ProcessLookupError:pass


def ipc(path,command):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(.3);connection.connect(str(path))
        connection.sendall((json.dumps({'command':command,'request_id':7})+'\n').encode())
        buffer=b''
        while len(buffer)<65536:
            chunk=connection.recv(4096)
            if not chunk:raise ConnectionError('Video player disconnected.')
            buffer+=chunk
            while b'\n' in buffer:
                line,buffer=buffer.split(b'\n',1);reply=json.loads(line)
                if reply.get('request_id')==7:return reply
        raise RuntimeError('Invalid video player reply.')


def launch(output,filename):
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',output):raise ValueError('Invalid monitor connector.')
    program=binary()
    if not program:raise RuntimeError('Build the video wallpaper component in Wallpaper Selector settings first.')
    path,info=inspect(filename)
    RUNTIME.mkdir(parents=True,exist_ok=True,mode=0o700)
    socket_root=Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))/'fusion-wallpapers'
    socket_root.mkdir(parents=True,exist_ok=True,mode=0o700)
    endpoint=socket_root/(hashlib.sha256((output+str(time.monotonic_ns())).encode()).hexdigest()[:16]+'.sock')
    options='config=no terminal=no msg-level=all=warn audio=no loop-file=inf hwdec=auto-copy panscan=1.0 input-ipc-server='+str(endpoint)
    log=os.open(RUNTIME/(output+'.log'),os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
    try:child=subprocess.Popen([program,'-p','-a','full','-o',options,output,str(path)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    finally:os.close(log)
    record=dict(pid=child.pid,start=process_start(child.pid),path=str(path),socket=str(endpoint),output=output)
    for _ in range(60):
        if child.poll() is not None:break
        try:
            if ipc(endpoint,['get_property','video-params']).get('data',{}).get('w',0)>0:return record
        except (OSError,ValueError,AttributeError):pass
        time.sleep(.1)
    stop_record(record)
    raise RuntimeError('The video player could not decode this file. Your previous wallpaper was kept.')


def records():return read(RUNTIME/'processes.json',{})


def clear(outputs):
    """Called only after a successful picture/theme transaction."""
    if not SELECTION.exists():return
    with (SELECTION.parent/'videos.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        value=selections();running=records()
        for output in outputs:
            stop_record(running.pop(output,None));value['outputs'].pop(output,None)
        write(SELECTION,value);write(RUNTIME/'processes.json',running)


def apply(output,filename,expected,backend):
    still=poster(filename)
    if output not in {m['name'] for m in monitors()}:raise ValueError('That display disconnected.')
    SELECTION.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (SELECTION.parent/'videos.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        value=selections();running=records();old=running.get(output)
        before_selection=copy.deepcopy(value);before_records=copy.deepcopy(running)
        new=launch(output,filename)
        try:
            current=backend.apply_wallpapers({output:dict(path=str(still),original=str(still),fit='cover')},expected,keep_video=True)
            value['outputs'][output]=dict(path=str(Path(filename).resolve()),poster=str(still))
            running[output]=new;write(SELECTION,value);write(RUNTIME/'processes.json',running)
        except Exception:
            stop_record(new)
            write(SELECTION,before_selection);write(RUNTIME/'processes.json',before_records)
            if 'current' in locals() and output in expected:
                try:backend.apply_wallpapers({output:expected[output]},current,keep_video=True)
                except Exception:pass
            raise
        stop_record(old)
        return current


def session():
    """Restore saved videos on login/hotplug; pause them while on battery."""
    import psutil
    from wallpaper import library
    runtime=Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))
    display=Path(os.environ.get('WAYLAND_DISPLAY','wayland-1'))
    if not display.is_absolute():display=runtime/display
    instance=runtime/'hypr'/os.environ.get('HYPRLAND_INSTANCE_SIGNATURE','')/'.socket.sock'
    paused=set();failures={};iteration=0;known=set();paper_generation=None
    paper_socket=runtime/'hypr'/os.environ.get('HYPRLAND_INSTANCE_SIGNATURE','')/'.hyprpaper.sock'
    def interrupted(*_):raise SystemExit(0)
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    try:
        while display.exists() and instance.exists():
            try:
                if not SELECTION.exists() or not paper_socket.exists():time.sleep(2);continue
                with (SELECTION.parent/'videos.lock').open('a') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX)
                    value=selections();running=records();before=copy.deepcopy(running)
                    # Keep video above the still fallback in the background
                    # layer, including after hyprpaper is restarted. Desktop
                    # icons remain in the separate bottom layer above both.
                    generation=paper_socket.stat().st_ino
                    if paper_generation is not None and generation!=paper_generation:
                        for record in running.values():stop_record(record)
                        running={}
                    paper_generation=generation
                    if iteration%5==0:known={m['name'] for m in monitors()}
                    # Preserve the static poster for disconnected or missing-media outputs.
                    for output,choice in value['outputs'].items():
                        record=running.get(output)
                        if output not in known:
                            stop_record(record);running.pop(output,None);continue
                        if not alive(record) and time.monotonic()-failures.get(output,0)>30:
                            try:running[output]=launch(output,choice['path'])
                            except Exception as error:failures[output]=time.monotonic();print(output+': '+str(error),flush=True)
                    battery=psutil.sensors_battery();pause=bool(battery and not battery.power_plugged and library.read().get('pause_on_battery',True))
                    for output,record in running.items():
                        if alive(record) and pause!=(record['pid'] in paused):
                            os.kill(record['pid'],signal.SIGSTOP if pause else signal.SIGCONT)
                            paused.add(record['pid']) if pause else paused.discard(record['pid'])
                    if running!=before:write(RUNTIME/'processes.json',running)
                iteration+=1
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:print(str(error),flush=True)
            time.sleep(2)
    finally:
        for record in records().values():stop_record(record)


if __name__=='__main__':session()
