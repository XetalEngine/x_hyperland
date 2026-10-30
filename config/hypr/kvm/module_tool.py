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
    entry=packages.installed('kvm-amd',directory)
    if not entry:raise RuntimeError('Download the matching custom KVM module in Paths & Tools first.')
    reason=packages.compatibility('kvm-amd',entry)
    if reason:raise RuntimeError(reason)
    path=directory/'components/kvm-amd/current'
    for name in ('kvm.ko','kvm-amd.ko'):
        magic=subprocess.check_output(['modinfo','-F','vermagic',str(path/name)],text=True).split()[0]
        if magic!=entry['kernel']:raise RuntimeError('Installed module ABI does not match its release metadata.')
    return path


def main():
    args=sys.argv[1:]
    if args and args[0] in ('--help','-h'):
        print('Usage: module-tool.sh [--check|--build-only|--install|--restore]\nDefault: load published modules for this boot only.');return
    if args not in ([],['--check'],['--build-only'],['--install'],['--restore']):raise ValueError('Unknown module option')
    directory=root()
    # Distro module backups must survive switching to a newer package version.
    os.environ['XETAL_KVM_MODULE_BACKUPS']=str(directory/'module-backups')
    if args==['--build-only']:
        raise RuntimeError('Published modules are prebuilt. Choose your own local build script in Paths & Tools to compile one.')
    path=check(directory)
    if args==['--check']:print('The published module matches this CPU and running kernel.');return
    os.execv('/usr/bin/bash',['bash',str(path/'load-kvm.sh'),*args])


if __name__=='__main__':
    try:main()
    except Exception as error:print('KVM: '+str(error),file=sys.stderr);raise SystemExit(1)
