"""Authenticated VNC/RDP hosting, owned by the current desktop user/session."""
import fcntl
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time

from .common import STATE, monitors, process_start, read, run, write

DIRECTORY = STATE/'remote-desktop'
DEFAULTS = dict(version=1, protocol='vnc', address='127.0.0.1', port=5900, output='', control=False,
                fps=30, username=getpass.getuser(), autostart=False)
TERMINAL_ESCAPE = re.compile(
    r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\|$)'
    r'|(?:\x1b\[|\x9b)[0-?]*[ -/]*(?:[@-~]|$)'
    r'|\x1b[@-_]')


def normalize(value):
    data = {**DEFAULTS, **value}
    if data['version'] != 1: raise ValueError('Unsupported remote desktop settings.')
    if data['protocol'] not in ('vnc','rdp'): raise ValueError('Choose VNC or RDP.')
    data['address'] = str(ipaddress.ip_address(data['address']))
    for key, low, high in [('port', 1024, 65535), ('fps', 5, 60)]:
        if type(data[key]) is not int or not low <= data[key] <= high: raise ValueError(f'Invalid {key}.')
    for key in ('control', 'autostart'):
        if type(data[key]) is not bool: raise ValueError(f'Invalid {key}.')
    if not re.fullmatch(r'[\w.@-]{1,64}', data['username']): raise ValueError('Use a short username with letters, numbers, dots or dashes.')
    if not isinstance(data['output'], str) or not re.fullmatch(r'[\w.:-]{0,128}', data['output']):
        raise ValueError('Choose a connected monitor.')
    return {key: data[key] for key in DEFAULTS}


def preferences(directory=DIRECTORY):
    return normalize(read(directory/'settings.json', DEFAULTS))


def addresses():
    result = ['127.0.0.1']
    try:
        for interface in json.loads(run(['ip', '-j', 'address', 'show'], timeout=4)):
            for info in interface.get('addr_info', []):
                address = info.get('local', '')
                if info.get('scope') == 'global' and info.get('family') == 'inet': result.append(address)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError): pass
    return list(dict.fromkeys(result))


def process(directory=DIRECTORY):
    data = read(directory/'process.json', {})
    pid = data.get('pid', 0)
    if not pid or process_start(pid) != data.get('start'): return None
    try:
        args = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        if str(directory/data.get('config','server.conf')).encode() not in args: return None
    except OSError: return None
    return data


def executable(protocol):
    if protocol=='vnc':return shutil.which('wayvnc')
    bundled=Path(__file__).resolve().parent/'.build/hypr-rdp/release/hypr-rdp'
    return str(bundled) if bundled.is_file() else shutil.which('hypr-rdp')


def listener_status(owned):
    """Inspect only this server's TCP sockets, without making a test connection."""
    if not owned: return dict(listening=False, connections=0)
    inodes = set()
    try:
        for fd in Path(f'/proc/{owned["pid"]}/fd').iterdir():
            try: target = fd.readlink().as_posix()
            except OSError: continue
            if target.startswith('socket:['): inodes.add(target[8:-1])
        listening, clients = False, 0
        for name in ('tcp', 'tcp6'):
            table = Path(f'/proc/{owned["pid"]}/net/{name}')
            if not table.exists(): continue
            for row in table.read_text().splitlines()[1:]:
                fields = row.split()
                if len(fields) < 10 or fields[9] not in inodes: continue
                if int(fields[1].rsplit(':', 1)[1], 16) != owned['port']: continue
                listening |= fields[3] == '0A'
                clients += fields[3] == '01'
        return dict(listening=bool(listening), connections=clients)
    except (OSError, ValueError, KeyError):
        return dict(listening=False, connections=0)


def status(directory=DIRECTORY):
    owned = process(directory)
    text = ''
    logfile = directory/'server.log'
    if logfile.exists():
        with logfile.open('rb') as stream:
            offset = max(0, logfile.stat().st_size-6000)
            if offset:
                # Start on a complete line, not in the middle of an ANSI escape
                # or a UTF-8 character in the bounded log tail.
                stream.seek(offset-1)
                if stream.read(1) != b'\n': stream.readline(6000)
            text = stream.read(6000).decode(errors='replace')
        # The Qt log pane is plain text. Clean existing/running-server logs too,
        # so applying this update never requires interrupting a sharing session.
        text = TERMINAL_ESCAPE.sub('', text).replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'[\x00-\x08\x0b-\x1f\x7f-\x9f]', '', text)
    return dict(running=bool(owned), process=owned, **listener_status(owned),
                installed=bool(executable(preferences(directory)['protocol'])), log=text)


def save(value, password='', directory=DIRECTORY):
    data = normalize(value)
    if password:
        if len(password) < 12 or len(password) > 256 or password!=password.strip() or any(c in password for c in '\r\n\0'):
            raise ValueError('Use a password of 12–256 characters without line breaks or leading/trailing spaces.')
        write(directory/'password', password)
    if not (directory/'password').is_file(): raise ValueError('Set a remote-access password first.')
    write(directory/'settings.json', data)
    return data


def certificate(directory):
    key, cert = directory/'tls-key.pem', directory/'tls-cert.pem'
    if not key.exists() or not cert.exists() or not key.stat().st_size or not cert.stat().st_size:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Pre-create private files instead of changing the multithreaded app's umask.
        for path in (key,cert):path.touch(mode=0o600,exist_ok=True);path.chmod(0o600)
        run(['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:secp384r1',
             '-sha384', '-days', '3650', '-nodes', '-keyout', key, '-out', cert,
             '-subj', '/CN=Hyper Fusion Remote Desktop'], timeout=25)
    key.chmod(0o600); cert.chmod(0o600)
    return run(['openssl', 'x509', '-in', cert, '-noout', '-fingerprint', '-sha256'])


def server_config(value, password, directory):
    data = normalize(value)
    if not password or any(c in password for c in '\r\n\0'): raise ValueError('Invalid remote-access password.')
    return '\n'.join(['enable_auth=true', 'relax_encryption=false', 'allow_broken_crypto=false',
        'username='+data['username'], 'password='+password,
        'private_key_file='+str(directory/'tls-key.pem'), 'certificate_file='+str(directory/'tls-cert.pem'), ''])


def start(directory=DIRECTORY):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory/'operation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if process(directory): raise ValueError('Stop the current sharing session before changing its settings.')
        data = preferences(directory)
        program = executable(data['protocol'])
        if not program: raise RuntimeError('Install the selected remote desktop component first.')
        if data['protocol']=='rdp' and not data['control']:
            raise ValueError('RDP shares keyboard and mouse control. Choose VNC for view-only sharing.')
        current = monitors()
        names = {m['name'] for m in current}
        if not names: raise RuntimeError('No active monitor is available to share.')
        if data['output'] and data['output'] not in names: raise RuntimeError('The selected monitor is disconnected.')
        output = data['output'] or next((m['name'] for m in current if m.get('focused')), current[0]['name'])
        if data['address'] not in addresses(): raise RuntimeError('The selected network address is unavailable. Choose an address on this computer.')
        fingerprint = certificate(directory)
        # One private control socket per desktop, never the global wayvncctl socket.
        socket_path = directory/'control.sock'
        socket_path.unlink(missing_ok=True)
        address = data['address'] if ':' not in data['address'] else '['+data['address']+']'
        config='server.conf' if data['protocol']=='vnc' else 'rdp.toml'
        if data['protocol']=='vnc':
            write(directory/config, server_config(data, (directory/'password').read_text(), directory))
            argv = [program, '-C', str(directory/config), '-S', str(socket_path),
                    '-o', output, '-f', str(data['fps']), '-n', 'Hyper Fusion', '-r', '-R']
            if not data['control']: argv.append('-d')
            argv.append(f'{address}:{data["port"]}')
        else:
            # Explicit configuration prevents inherited PAM/unauthenticated modes,
            # headless outputs, shell hooks and default clipboard file transfer.
            settings=dict(auth_mode='configured',bind=f'{address}:{data["port"]}',username=data['username'],
                password_file=str(directory/'password'),cert=str(directory/'tls-cert.pem'),key=str(directory/'tls-key.pem'),
                output=output,fps=data['fps'],audio_mode='mirror',keyboard_layout_policy='compositor',file_transfer_mode='off')
            write(directory/config,'\n'.join(key+' = '+json.dumps(value) for key,value in settings.items())+'\n')
            argv=[program,'--config',str(directory/config)]
        log = os.open(directory/'server.log', os.O_CREAT|os.O_WRONLY|os.O_TRUNC, 0o600)
        try:
            child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                     env=dict(os.environ, NO_COLOR='1'), start_new_session=True)
        finally: os.close(log)
        record = dict(pid=child.pid, start=process_start(child.pid), output=output,config=config,protocol=data['protocol'],
                      address=data['address'], port=data['port'], control=data['control'], fingerprint=fingerprint)
        write(directory/'process.json', record)
        for _ in range(30):
            if child.poll() is not None:
                (directory/'process.json').unlink(missing_ok=True)
                raise RuntimeError(status(directory)['log'].strip()[-1600:] or 'Remote desktop could not start.')
            if listener_status(record)['listening'] and (data['protocol']=='rdp' or socket_path.exists()):
                watch_session(directory); return record
            time.sleep(.1)
        stop(directory)
        raise RuntimeError('Remote desktop did not become ready. Check the connection log.')


def stop(directory=DIRECTORY):
    owned = process(directory)
    if owned:
        try: os.kill(owned['pid'], signal.SIGTERM)
        except ProcessLookupError: pass
        for _ in range(30):
            if not process(directory): break
            time.sleep(.1)
        if process(directory): raise RuntimeError('The sharing process has not stopped yet. Retry Stop sharing.')
    (directory/'process.json').unlink(missing_ok=True)
    return status(directory)


def autostart():
    if preferences()['autostart'] and not process(): return start()


def watch_session(directory):
    """A server must stop at logout even if its capture thread survives disconnect."""
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,PYTHONPATH=str(root))
    subprocess.Popen([sys.executable,'-m','desktop_services.remote','--watch',str(directory)],
                     env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)


def guard(directory):
    owned=process(directory)
    if not owned:return
    runtime=Path(os.environ.get('XDG_RUNTIME_DIR','/run/user/'+str(os.getuid())))
    display=runtime/os.environ.get('WAYLAND_DISPLAY','wayland-1')
    instance=runtime/'hypr'/os.environ.get('HYPRLAND_INSTANCE_SIGNATURE','')/'.socket.sock'
    try:
        original=(display.stat().st_ino,instance.stat().st_ino)
        while process(directory)==owned:
            time.sleep(1)
            if (display.stat().st_ino,instance.stat().st_ino)!=original:break
        else:return
    except OSError:pass
    if process(directory)==owned:stop(directory)


if __name__ == '__main__':
    try:
        if len(sys.argv)==3 and sys.argv[1]=='--watch':guard(Path(sys.argv[2]))
        else:autostart()
    except Exception as error: print(str(error), flush=True)
