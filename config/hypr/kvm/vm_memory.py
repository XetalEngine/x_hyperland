"""Authenticated executable images held in locked anonymous Linux memory.

The owning process keeps every image mapped and locked for the child's entire
lifetime. There is deliberately no temporary-file or unlocked-memory fallback.
"""
import base64
import ctypes
import errno
import fcntl
import hashlib
import json
import mmap
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC=b'XVM1\x00\x00\x00\x00'
MAX_IMAGE=1024**3
LIBC=ctypes.CDLL(None,use_errno=True)


def private_memory():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    if LIBC.prctl(4,0,0,0,0): raise OSError(ctypes.get_errno(),'Cannot disable runtime dumps')
    soft,hard=resource.getrlimit(resource.RLIMIT_MEMLOCK)
    if os.geteuid()==0:
        resource.setrlimit(resource.RLIMIT_MEMLOCK,(resource.RLIM_INFINITY,resource.RLIM_INFINITY))
    elif soft!=hard:
        resource.setrlimit(resource.RLIMIT_MEMLOCK,(hard,hard))
    if LIBC.mlockall(1|2):
        raise RuntimeError('The VM runtime needs permission to reserve locked memory. Start it from KVM Settings.')


def aad(edition,component,name):
    return ('XetalVM/1\0'+edition+'\0'+component+'\0'+name).encode()


class Image:
    def __init__(self, path, entry, key, associated):
        self.fd=-1;self.mapping=None
        size=entry['size']
        if type(size) is not int or not 1<=size<=MAX_IMAGE: raise ValueError('Invalid VM image size')
        path=Path(path)
        if path.stat().st_size!=size+36: raise ValueError('VM component size does not match')
        # The caller has already locked its entire address space. Do not copy
        # plaintext through Python bytes, a named tempfile, tmpfs or stdout.
        try:
            self.fd=os.memfd_create('xetal-vm',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
            os.ftruncate(self.fd,size+15)
            self.mapping=mmap.mmap(self.fd,size+15)
            address=ctypes.addressof(ctypes.c_char.from_buffer(self.mapping))
            if LIBC.mlock(ctypes.c_void_p(address),ctypes.c_size_t(size+15)):
                raise RuntimeError('Cannot reserve locked memory for this VM component.')
            self.mapping.madvise(mmap.MADV_DONTDUMP)
            with path.open('rb') as source:
                header=source.read(20)
                if header[:8]!=MAGIC: raise ValueError('Unsupported VM component format')
                source.seek(-16,os.SEEK_END);tag=source.read(16);source.seek(20)
                decryptor=Cipher(algorithms.AES(key),modes.GCM(header[8:],tag)).decryptor()
                decryptor.authenticate_additional_data(associated)
                checksum=hashlib.sha256(header);offset=0
                while offset<size:
                    chunk=source.read(min(1024*1024,size-offset))
                    if not chunk: raise ValueError('Incomplete VM component')
                    checksum.update(chunk)
                    output=memoryview(self.mapping)[offset:offset+len(chunk)+15]
                    try: count=decryptor.update_into(chunk,output)
                    finally: output.release()
                    if count!=len(chunk): raise ValueError('Invalid VM component block')
                    offset+=count
                decryptor.finalize()  # Authenticate before executing or loading.
                checksum.update(tag)
                if checksum.hexdigest()!=entry['sha256']: raise ValueError('VM component checksum does not match')
            os.ftruncate(self.fd,size)
            # FUTURE_WRITE preserves this private writable owner mapping so it
            # remains pinned, but prevents new writable mappings and write(2).
            seals=fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL|0x0010
            fcntl.fcntl(self.fd,fcntl.F_ADD_SEALS,seals)
        except Exception:
            self.close();raise

    @property
    def path(self): return f'/proc/self/fd/{self.fd}'

    def close(self):
        if self.mapping is not None:
            # Wipe through the retained mapping before dropping its lock.
            address=ctypes.addressof(ctypes.c_char.from_buffer(self.mapping))
            ctypes.memset(address,0,os.fstat(self.fd).st_size)
            self.mapping.close();self.mapping=None
        if self.fd>=0: os.close(self.fd);self.fd=-1

    def __enter__(self): return self
    def __exit__(self,*_): self.close()


def run_pinned(command, images):
    child=subprocess.Popen(command,pass_fds=tuple(image.fd for image in images))
    previous={}
    def forward(number,_):
        if child.poll() is None: child.send_signal(number)
    try:
        for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
            previous[number]=signal.signal(number,forward)
        code=child.wait()
        return code if code>=0 else 128-code
    finally:
        if child.poll() is None: child.terminate();child.wait()
        for number,handler in previous.items(): signal.signal(number,handler)


def load_image(component, name, *, key=None):
    component=Path(component)
    descriptor=json.loads((component/'.vm-runtime.json').read_text())
    from packages import validate_runtime
    validate_runtime(descriptor,descriptor.get('component'))
    entry=descriptor['files'][name]
    path=component/entry['file']
    if not path.resolve().is_relative_to(component.resolve()): raise ValueError('Invalid VM component path')
    if key is None:
        from runtime_access import launch_key
        key=launch_key(descriptor['key_id'],descriptor['edition'])
    return Image(path,entry,key,aad(descriptor['edition'],descriptor['component'],name))


def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    component=Path(sys.argv[1]).resolve()
    from vm_session import receive_image
    fd=receive_image(component,'libexec/qemu-system-x86_64')
    os.set_inheritable(fd,True)
    loaders=list((component/'lib').glob('ld-linux-*.so.*'))
    if len(loaders)!=1: raise RuntimeError('The QEMU runtime loader is missing.')
    command=[str(loaders[0]),'--library-path',str(component/'lib'),'--argv0','qemu-system-x86_64',f'/proc/self/fd/{fd}',
             '-L',str(component/'share/qemu'),*sys.argv[2:]]
    os.execv(command[0],command)


if __name__=='__main__':
    try: sys.exit(main())
    except Exception as error:
        print('KVM: '+str(error),file=sys.stderr);sys.exit(1)
