"""Opt-in root fixture: synthetic token, tiny /usr/bin/true image, no networking.

Run with sudo python3 test_memory_runtime.py --offline-fixture. No VM, sysfs,
kernel-module, service or user-profile operation is performed.
"""
import array
from contextlib import ExitStack
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
from unittest.mock import patch
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import hashlib
import vm_memory
import vm_session
import runtime_access
import module_image
import module_state


def main():
    if sys.argv[1:]!=['--offline-fixture'] or os.geteuid()!=0:
        raise SystemExit('Explicit --offline-fixture and root are required.')
    with tempfile.TemporaryDirectory(prefix='xetal-memory-fixture-') as directory:
        root=Path(directory);component=root/'components/qemu';component.mkdir(parents=True)
        data=Path('/usr/bin/true').read_bytes();key=os.urandom(32);nonce=os.urandom(12)
        blob=vm_memory.MAGIC+nonce+AESGCM(key).encrypt(nonce,data,vm_memory.aad('xetallic','qemu','libexec/qemu-system-x86_64'))
        path=component/'fixture.xvm';path.write_bytes(blob)
        entry={'size':len(data),'sha256':hashlib.sha256(blob).hexdigest()}
        vm_memory.private_memory()
        runtime_access.arm(root,'synthetic-offline-token')
        try:
            with patch.dict(os.environ,{'XETAL_KVM_DATA':str(root)}),patch('echo_account.request',return_value={'key':__import__('base64').b64encode(key).decode()}) as request:
                assert runtime_access.launch_key('a'*64,'xetallic')==key
                assert request.call_args.args[1]['token']=='synthetic-offline-token'
            with vm_memory.Image(path,entry,key,vm_memory.aad('xetallic','qemu','libexec/qemu-system-x86_64')) as image:
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
                    endpoint=str(root/'images.sock');listener.bind(endpoint);listener.listen(2)
                    threading.Thread(target=vm_session.serve,args=(listener,{(str(component),'libexec/qemu-system-x86_64'):image}),daemon=True).start()
                    with patch.dict(os.environ,{'XETAL_KVM_LAUNCH_SOCKET':endpoint}):
                        fd=vm_session.receive_image(component,'libexec/qemu-system-x86_64')
                        try:
                            assert os.read(fd,len(data))==data
                            assert vm_memory.run_pinned([image.path],[image])==0
                        finally:os.close(fd)
            assert not (component/'libexec/qemu-system-x86_64').exists()
            # Exercise the Windows handoff with authenticated module metadata,
            # real locked memfds and a root-owned receipt in disposable sysfs.
            # These are synthetic ELF metadata fixtures, never kernel-loaded.
            from test_module_image import elf
            import platform
            modules=root/'modules';modules.mkdir()
            sysfs=root/'sys-module';versions={}
            for name,filename in (('kvm','kvm.ko'),('kvm_amd','kvm-amd.ko')):
                version=('A' if name=='kvm' else 'B')*24
                plain=elf((platform.release()+' SMP').encode(),version.encode())
                associated=vm_memory.aad('xetallic','kvm-amd',filename)
                nonce=os.urandom(12)
                encrypted=vm_memory.MAGIC+nonce+AESGCM(key).encrypt(nonce,plain,associated)
                image_path=modules/(filename+'.xvm');image_path.write_bytes(encrypted)
                info={'size':len(plain),'sha256':hashlib.sha256(encrypted).hexdigest()}
                with vm_memory.Image(image_path,info,key,associated) as image:
                    assert module_image.vermagic(image.fd).split()[0]==platform.release()
                    versions[name]=module_image.modinfo(image.fd,'srcversion')
                (sysfs/name).mkdir(parents=True)
                (sysfs/name/'srcversion').write_text(version+'\n')
                assert not (modules/filename).exists()
            parameter=sysfs/'kvm_amd/parameters/intercept_cpuid'
            parameter.parent.mkdir();parameter.write_text('Y\n')
            with patch.object(module_state,'RECEIPT',root/'module-receipt.json'), \
                 patch.object(module_state,'SYS_MODULE',sysfs):
                module_state.record_loaded(platform.release(),versions)
                assert module_state.verified()['srcversions']==versions
            print('Root memory/keyring/descriptor/execution and encrypted module identity fixtures passed; no network or kernel modules used.')
        finally:runtime_access.revoke(root)


if __name__=='__main__':main()
