"""Bounded ELF64 module metadata and finit_module(2), without named images."""
import ctypes
import os
import platform
import re
import struct
import sys


def read(fd, offset, count):
    size=os.fstat(fd).st_size
    if offset<0 or count<0 or count>16*1024*1024 or offset>size-count:
        raise ValueError('Invalid module ELF bounds')
    data=os.pread(fd,count,offset)
    if len(data)!=count:raise ValueError('Incomplete module ELF')
    return data


def modinfo(fd, field):
    if field not in ('vermagic', 'srcversion'):
        raise ValueError('Unsupported module metadata field')
    header=read(fd,0,64)
    if header[:7]!=b'\x7fELF\x02\x01\x01' or struct.unpack_from('<HH',header,16)!=(1,62):
        raise ValueError('Expected an x86-64 Linux module')
    offset=struct.unpack_from('<Q',header,40)[0]
    entry_size,count,names_index=struct.unpack_from('<HHH',header,58)
    if entry_size!=64 or not 1<=count<=65535 or not 0<names_index<count:
        raise ValueError('Invalid module ELF sections')
    sections=read(fd,offset,count*64)
    def section(index):return struct.unpack_from('<IIQQQQIIQQ',sections,index*64)
    names_section=section(names_index)
    names=read(fd,names_section[4],names_section[5])
    for index in range(count):
        item=section(index)
        if item[0]>=len(names):raise ValueError('Invalid module section name')
        end=names.find(b'\0',item[0])
        if end<0:raise ValueError('Invalid module section name')
        if names[item[0]:end]==b'.modinfo':
            entries=read(fd,item[4],item[5]).split(b'\0')
            prefix=(field+'=').encode('ascii')
            values=[entry[len(prefix):].decode('ascii') for entry in entries if entry.startswith(prefix)]
            if len(values)!=1 or not values[0].split() or len(values[0])>512:
                raise ValueError('Invalid module '+field+' metadata')
            if field == 'srcversion' and not re.fullmatch(r'[A-Fa-f0-9]{24}', values[0]):
                raise ValueError('Invalid module srcversion metadata')
            return values[0]
    raise ValueError('Module '+field+' metadata is missing')


def vermagic(fd):
    return modinfo(fd, 'vermagic')


def load(fd, parameters):
    if os.geteuid()!=0 or platform.machine()!='x86_64':raise RuntimeError('This module requires an x86-64 Linux administrator.')
    if vermagic(fd).split()[0]!=platform.release():raise RuntimeError('Module ABI does not match this kernel.')
    if any(not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*=[A-Za-z0-9_,+-]+',p) for p in parameters):
        raise ValueError('Invalid module parameter')
    libc=ctypes.CDLL(None,use_errno=True);libc.syscall.restype=ctypes.c_long
    # x86-64 __NR_finit_module; flags=0 retains kernel signature/ABI checks.
    result=libc.syscall(ctypes.c_long(313),ctypes.c_int(fd),ctypes.c_char_p(' '.join(parameters).encode()),ctypes.c_int(0))
    if result!=0:raise OSError(ctypes.get_errno(),'The kernel rejected this module')


if __name__=='__main__':
    try:
        # Metadata is read from the plaintext image too. Keep even these small
        # copies out of swap/core dumps in the short-lived helper process.
        from vm_memory import private_memory
        private_memory()
        action=sys.argv[1];fd=int(sys.argv[2])
        if action=='check':
            if vermagic(fd).split()[0]!=sys.argv[3]:raise RuntimeError('Module ABI does not match its release.')
        elif action=='load':load(fd,sys.argv[3:])
        else:raise ValueError('Unknown module action')
    except Exception as error:
        print('KVM: '+str(error),file=sys.stderr);sys.exit(1)
