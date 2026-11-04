#!/usr/bin/env python3
"""Own a launch's resident images before any GPU handoff or host changes."""
import argparse
import array
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import re
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import editions
import portable
from vm_memory import private_memory,load_image,run_pinned


def receive_image(component,name):
    endpoint=os.environ.get('XETAL_KVM_LAUNCH_SOCKET','')
    if not endpoint: raise RuntimeError('Start this edition from KVM Settings.')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(15);client.connect(endpoint)
        _,uid,_=struct.unpack('3i',client.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if uid!=0: raise RuntimeError('Invalid VM launch owner')
        client.sendall(json.dumps([str(Path(component).resolve()),name]).encode()+b'\n')
        message,controls,flags,_=client.recvmsg(256,socket.CMSG_SPACE(array.array('i').itemsize))
        received=[]
        for level,kind,data in controls:
            if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                values=array.array('i');values.frombytes(data[:len(data)//values.itemsize*values.itemsize]);received.extend(values)
        if message!=b'OK' or len(received)!=1 or flags & socket.MSG_CTRUNC:
            for fd in received: os.close(fd)
            raise RuntimeError('The VM launch session is unavailable.')
        return received[0]


def serve(listener,images):
    while True:
        try: client,_=listener.accept()
        except OSError:return
        with client:
            client.settimeout(5)
            try:
                _,uid,_=struct.unpack('3i',client.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                if uid!=0:continue
                body=b''
                while b'\n' not in body and len(body)<=8192:
                    chunk=client.recv(1024)
                    if not chunk:break
                    body+=chunk
                if len(body)>8192:continue
                key=json.loads(body)
                image=images.get(tuple(key)) if isinstance(key,list) and len(key)==2 and all(isinstance(v,str) for v in key) else None
                if image is None:client.sendall(b'Unavailable');continue
                client.sendmsg([b'OK'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[image.fd]))])
            except (OSError,ValueError,TypeError):continue


def main(command,module_options=None,*,components=('qemu','kvm-amd'),revoke_session=True):
    if not command:raise ValueError('Missing VM launch command')
    if editions.selected()=='stock':
        system_kvm()
        os.execv(command[0],command)
    private_memory()
    if os.geteuid()!=0:raise RuntimeError('Administrator access is required for this VM launch.')
    with ExitStack() as stack:
        images={}
        for component in components:
            path=portable.component_path(component).resolve()
            descriptor=path/'.vm-runtime.json'
            if component=='kvm-amd' and not descriptor.is_file():continue
            data=json.loads(descriptor.read_text())
            from runtime_access import launch_key
            key=launch_key(data['key_id'],data['edition'])
            for name in data['files']:
                images[(str(path),name)]=stack.enter_context(load_image(path,name,key=key))
        # No token is needed after all images are authenticated and resident.
        from runtime_access import revoke
        if revoke_session:revoke(portable.data_root())
        directory=Path(tempfile.mkdtemp(prefix='xetal-vm-',dir='/run'))
        try:
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
                endpoint=str(directory/'images.sock');listener.bind(endpoint);os.chmod(endpoint,0o600);listener.listen(8)
                threading.Thread(target=serve,args=(listener,images),daemon=True).start()
                os.environ['XETAL_KVM_LAUNCH_SOCKET']=endpoint
                if module_options is not None:
                    if (not isinstance(module_options,dict) or len(module_options)>64
                            or any(not re.fullmatch(r'KVM_[A-Z0-9_]+',str(k))
                                   or not isinstance(v,(str,int,bool)) for k,v in module_options.items())):
                        raise ValueError('Invalid custom module settings.')
                    environment=dict(os.environ,**{k:str(v) for k,v in module_options.items() if str(v)})
                    subprocess.run([sys.executable,str(portable.ROOT/'module_tool.py')],env=environment,check=True)
                return run_pinned(command,[])
        finally:shutil.rmtree(directory)


def system_kvm():
    """Drop a previously loaded custom module before starting Stock, if idle."""
    indicator=Path('/sys/module/kvm_amd/parameters/private_msr_gp_burst')
    if not indicator.exists():return
    if os.geteuid()!=0:raise RuntimeError('Administrator access is required to select system KVM.')
    for line in Path('/proc/modules').read_text().splitlines():
        fields=line.split()
        if fields[0]=='kvm_amd' and fields[2]!='0':
            raise RuntimeError('Shut down other virtual machines before switching to Basic free.')
    for args in (['modprobe','-r','kvm_amd'],['modprobe','-r','kvm'],['modprobe','kvm_amd']):
        subprocess.run(args,check=True,capture_output=True)
    if indicator.exists():
        raise RuntimeError('The system module was previously replaced. Restore the distribution KVM module before starting Basic free.')


if __name__=='__main__':
    try:
        parser=argparse.ArgumentParser()
        parser.add_argument('--module-options')
        parser.add_argument('command',nargs=argparse.REMAINDER)
        args=parser.parse_args()
        command=args.command
        if command[:1]==['--']:command=command[1:]
        sys.exit(main(command,json.loads(args.module_options) if args.module_options is not None else None))
    except Exception as error:
        print('KVM: '+str(error),file=sys.stderr);sys.exit(1)
