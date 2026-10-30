"""Transactional GRUB edit invoked only by the wizard's explicit Apply action."""
from pathlib import Path
import argparse
import fcntl
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import uuid


def replace(path,content,mode_from):
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as output:
            output.write(content);output.flush();os.fsync(output.fileno())
        shutil.copystat(mode_from,name)
        stat=Path(mode_from).stat()
        if os.geteuid()==0:os.chown(name,stat.st_uid,stat.st_gid)
        os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)


def apply(config,boot_config,expected,cmdline,regen):
    config,boot_config=Path(config),Path(boot_config)
    if config.is_symlink() or boot_config.is_symlink():
        raise ValueError('GRUB configuration is a symlink; edit this layout manually.')
    with config.with_name(config.name+'.xetal-kvm.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        original=config.read_bytes()
        if hashlib.sha256(original).hexdigest()!=expected:
            raise ValueError('GRUB changed since the wizard preview. Refresh the IOMMU step and review it again.')
        text=original.decode()
        expression=r'^\s*GRUB_CMDLINE_LINUX_DEFAULT=.*$'
        if len(re.findall(expression,text,re.M))>1:
            raise ValueError('Multiple GRUB command-line assignments; edit this layout manually.')
        line='GRUB_CMDLINE_LINUX_DEFAULT='+shlex.quote(cmdline)
        updated=re.sub(expression,lambda _:line,text,flags=re.M) if re.search(expression,text,re.M) else text.rstrip()+'\n'+line+'\n'
        stamp=uuid.uuid4().hex[:12]
        backup=config.with_name(config.name+'.xetal-kvm-bak-'+stamp)
        shutil.copy2(config,backup)
        boot_backup=None
        if boot_config.exists():
            boot_backup=boot_config.with_name(boot_config.name+'.xetal-kvm-bak-'+stamp)
            shutil.copy2(boot_config,boot_backup)
        print('Backup: '+str(backup),flush=True)
        try:
            replace(config,updated.encode(),backup)
            subprocess.run(regen,check=True,timeout=150)
        except BaseException:
            replace(config,original,backup)
            if boot_backup:replace(boot_config,boot_backup.read_bytes(),boot_backup)
            else:boot_config.unlink(missing_ok=True)
            print('GRUB generation failed; both previous configurations were restored.',flush=True)
            raise
        print('IOMMU boot configuration saved. Reboot to apply.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('config','boot-config','expected','cmdline'):parser.add_argument('--'+name,required=True)
    parser.add_argument('regen',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    try:apply(args.config,args.boot_config,args.expected,args.cmdline,args.regen[1:] if args.regen[:1]==['--'] else args.regen)
    except Exception as error:parser.exit(1,str(error)+'\n')
