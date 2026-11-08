#!/usr/bin/env python3
"""Explicit custom-module operation; downloading a component never calls this."""
from pathlib import Path
import os
import pwd
import sys
import subprocess
import packages
import portable


def root():
    if os.geteuid()==0 and os.environ.get('SUDO_USER') and not os.environ.get('XETAL_KVM_DATA'):
        return Path(pwd.getpwnam(os.environ['SUDO_USER']).pw_dir)/'.local/share/xetal-kvm'
    return portable.data_root()


def check(directory):
    import editions
    base=editions.component_root(directory)
    entry=packages.installed('kvm-amd',base)
    if not entry:raise RuntimeError('Download the matching custom KVM module in Paths & Tools first.')
    reason=packages.compatibility('kvm-amd',entry)
    if reason:raise RuntimeError(reason)
    path=base/'components/kvm-amd/current'
    if entry.get('runtime'):
        packages.prepare_runtime('kvm-amd',entry,path)
        return path
    for name in ('kvm.ko','kvm-amd.ko'):
        magic=subprocess.check_output(['modinfo','-F','vermagic',str(path/name)],text=True).split()[0]
        if magic!=entry['kernel']:raise RuntimeError('Installed module ABI does not match its release metadata.')
    return path


def main():
    args=sys.argv[1:]
    if args and args[0] in ('--help','-h'):
        print('Usage: module-tool.sh [--auto|--check|--build-only|--install|--restore]\nDefault: load published modules for this boot only.');return
    if args not in ([],['--auto'],['--check'],['--build-only'],['--install'],['--restore']):raise ValueError('Unknown module option')
    directory=root()
    if args == ['--auto']:
        from module_policy import unavailable
        reason = unavailable(directory)
        if reason:
            print('KVM: '+reason+'. Continuing with the loaded/system KVM module.', flush=True)
            return
        args = []
    # Distro module backups must survive switching to a newer package version.
    os.environ['XETAL_KVM_MODULE_BACKUPS']=str(directory/'module-backups')
    if args==['--build-only']:
        raise RuntimeError('Published modules are prebuilt. Choose your own local build script in Paths & Tools to compile one.')
    path=check(directory)
    if args==['--check']:print('The published module matches this CPU and running kernel.');return
    entry=packages.read_json(path/'.component.json',{})
    if entry.get('runtime') and args!=['--restore']:
        if args==['--install']:raise RuntimeError('This edition supports loading the custom module for the current boot only.')
        from vm_session import receive_image
        from vm_memory import private_memory
        from module_image import vermagic, modinfo
        from module_state import record_loaded
        private_memory()
        descriptors=[]
        try:
            for name in ('kvm.ko','kvm-amd.ko'):descriptors.append(receive_image(path,name))
            for fd in descriptors:
                if vermagic(fd).split()[0]!=entry['kernel']:
                    raise RuntimeError('Module ABI does not match its release metadata.')
            srcversions={name:modinfo(fd,'srcversion')
                         for name,fd in zip(('kvm','kvm_amd'),descriptors)}
            environment=dict(os.environ,XETAL_KVM_MEMORY_MODULES='1',
                XETAL_KVM_CORE_IMAGE=str(descriptors[0]),XETAL_KVM_AMD_IMAGE=str(descriptors[1]),
                XETAL_KVM_IMAGE_HELPER=str(portable.ROOT/'module_image.py'))
            reply=subprocess.run(['/usr/bin/bash',str(path/'load-kvm.sh')],env=environment,pass_fds=descriptors)
            if reply.returncode == 0:
                record_loaded(entry['kernel'],srcversions)
            raise SystemExit(reply.returncode)
        finally:
            for fd in descriptors:os.close(fd)
    os.execv('/usr/bin/bash',['bash',str(path/'load-kvm.sh'),*args])


if __name__=='__main__':
    try:main()
    except Exception as error:print('KVM: '+str(error),file=sys.stderr);raise SystemExit(1)
