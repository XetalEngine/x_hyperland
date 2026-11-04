"""Short-lived root-owned launch authorization in the Linux kernel keyring.

Only a key serial (not credentials) appears in the private runtime marker.
Kernel keys survive a Single GPU display-manager shutdown and expire on their
own. The account token and content keys are never written to disk here.
"""
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
from vm_memory import private_memory

LIB=ctypes.CDLL('libkeyutils.so.1',use_errno=True)
LIB.add_key.restype=ctypes.c_int32
LIB.add_key.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int32]
LIB.keyctl_read.restype=ctypes.c_long
LIB.keyctl_read.argtypes=[ctypes.c_int32,ctypes.c_void_p,ctypes.c_size_t]
LIB.keyctl_setperm.argtypes=[ctypes.c_int32,ctypes.c_uint32]
LIB.keyctl_set_timeout.argtypes=[ctypes.c_int32,ctypes.c_uint32]
LIB.keyctl_link.argtypes=[ctypes.c_int32,ctypes.c_int32]


def marker(root):
    identity=hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()
    return Path('/run/xetal-kvm-auth')/(identity+'.json')


def arm(root, token):
    if os.geteuid()!=0: raise RuntimeError('Administrator access is required to prepare this VM.')
    if not isinstance(token,str) or not 1<=len(token)<=128: raise ValueError('Invalid Echo session')
    private_memory()
    directory=marker(root).parent
    directory.mkdir(mode=0o700,exist_ok=True)
    if directory.is_symlink() or directory.stat().st_uid!=0 or directory.stat().st_mode&0o077:
        raise RuntimeError('The VM runtime directory has unsafe permissions.')
    blob=token.encode();description=('xetal-vm:'+hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()).encode()
    # Create while possessed by this sudo session, then grant root explicit
    # owner access before linking into root's user keyring for the VM service.
    serial=LIB.add_key(b'user',description,blob,len(blob),-3)
    if serial<0: raise RuntimeError('The kernel session keyring is unavailable. VM launch was stopped.')
    # Root owns it: search/read/update/link only for its owner. No possessor,
    # group or other access, even if another process learns the serial.
    if LIB.keyctl_setperm(serial,0x003f0000) or LIB.keyctl_set_timeout(serial,180) or LIB.keyctl_link(serial,-4):
        LIB.keyctl_revoke(serial);raise RuntimeError('Could not prepare the VM launch session.')
    from packages import atomic_json
    atomic_json(marker(root),{'serial':serial})
    marker(root).chmod(0o600)


def launch_key(key_id, edition):
    if os.geteuid()!=0: raise RuntimeError('Start this edition from KVM Settings.')
    from portable import data_root
    try: serial=int(json.loads(marker(data_root()).read_text())['serial'])
    except (OSError,ValueError,KeyError): raise RuntimeError('Sign in to Echo and start the VM from KVM Settings.') from None
    buffer=ctypes.create_string_buffer(129)
    count=LIB.keyctl_read(serial,buffer,128)
    if not 1<=count<=128: raise RuntimeError('The launch session expired. Start the VM again from KVM Settings.')
    try:
        from echo_account import request
        response=request('launch',{'token':buffer.raw[:count].decode(),'edition':edition,'key_id':key_id})
        key=base64.b64decode(response['key'],validate=True)
        if len(key)!=32: raise ValueError('Invalid launch response')
        return key
    finally: ctypes.memset(buffer,0,129)


def revoke(root):
    try:
        serial=int(json.loads(marker(root).read_text())['serial'])
        LIB.keyctl_revoke(serial)
    except (OSError,ValueError,KeyError):pass
    marker(root).unlink(missing_ok=True)


if __name__=='__main__':
    try:
        private_memory()
        data=json.loads(sys.stdin.buffer.read(1024))
        arm(sys.argv[1],data['token'])
    except Exception as error:
        print('KVM: '+str(error),file=sys.stderr);sys.exit(1)
