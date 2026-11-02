#!/usr/bin/env python3
"""Boot generated entries in disposable QEMU images; never attach host disks.

Explicit integration check (not part of ordinary unit-test discovery). Needs
QEMU, GRUB BIOS/EFI tools, OVMF, xorriso, mtools and mke2fs. Runs without root.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import grub_editor as grub

SERIAL = 'serial --unit=0 --speed=115200\nterminal_output serial\n'


def run(*args):
    result=subprocess.run(list(map(str,args)),capture_output=True,timeout=60)
    if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace')[-3000:])


def boot(root, name, drives, marker, firmware=(), qemu=None):
    log=root/(name+'.log')
    qemu=qemu or shutil.which('qemu-system-x86_64')
    args=[qemu,'-no-user-config','-machine','q35,accel=tcg','-m','256','-display','none','-monitor','none','-parallel','none',
          '-serial','file:'+str(log),'-nic','none','-no-reboot',*firmware,*drives]
    process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        until=time.monotonic()+35
        while time.monotonic()<until:
            markers = [marker] if isinstance(marker, str) else marker
            if log.exists() and all(value in log.read_text(errors='replace') for value in markers):
                print('PASS:',name,flush=True);return
            if process.poll() is not None:break
            time.sleep(.1)
    finally:
        if process.poll() is None:process.terminate()
        try:_,errors=process.communicate(timeout=5)
        except subprocess.TimeoutExpired:process.kill();_,errors=process.communicate()
    raise RuntimeError(name+' did not reach its bootloader.\n'+errors.decode(errors='replace')+'\n'+
                       (log.read_text(errors='replace')[-4000:] if log.exists() else 'No serial output.'))


def main():
    with tempfile.TemporaryDirectory(prefix='fusion-grub-boot-') as directory:
        root=Path(directory)
        # UEFI: a real GRUB EFI program chainloads a second EFI program using
        # precisely the same rendered command used for Windows/shim loaders.
        fat=root/'efi.img'
        with fat.open('wb') as stream:stream.truncate(128*1024*1024)
        run('mkfs.fat','-F','32','-i','CABF1234',fat)
        target=root/'target.cfg';target.write_text(SERIAL+'echo FUSION_EFI_TARGET_REACHED\nhalt\n')
        loader=root/'target.efi'
        run('grub-mkstandalone','-O','x86_64-efi','-o',loader,'boot/grub/grub.cfg='+str(target))
        item={'kind':'efi','uuid':'CABF-1234','partuuid':'','loader':'/EFI/target/grubx64.efi','filesystem':'vfat','name':"Test's Windows / Linux"}
        item['id']=grub.entry_id(item)
        start=root/'start.cfg';start.write_text(SERIAL+'set default=0\nset timeout=0\n'+grub.render_entry(item))
        first=root/'bootx64.efi'
        run('grub-mkstandalone','-O','x86_64-efi','-o',first,'boot/grub/grub.cfg='+str(start))
        run('mmd','-i',fat,'::/EFI','::/EFI/BOOT','::/EFI/target')
        run('mcopy','-i',fat,first,'::/EFI/BOOT/BOOTX64.EFI')
        run('mcopy','-i',fat,loader,'::/EFI/target/grubx64.efi')
        ovmf=next(Path(p) for p in ('/usr/share/OVMF/OVMF_CODE.fd','/usr/share/edk2/x64/OVMF_CODE.4m.fd') if Path(p).is_file())
        vars_source=ovmf.with_name(ovmf.name.replace('CODE','VARS'))
        variables=root/'vars.fd';shutil.copyfile(vars_source,variables)
        boot(root,'UEFI chainload',['-drive',f'file={fat},format=raw'], 'FUSION_EFI_TARGET_REACHED',
             ['-drive',f'if=pflash,format=raw,readonly=on,file={ovmf}','-drive',f'if=pflash,format=raw,file={variables}'])
        # A missing UUID must not chainload a same-named file on the previous root.
        item['uuid']='DEAD-BEEF';item['id']=grub.entry_id(item)
        start.write_text(SERIAL+"search --fs-uuid --set=root CABF-1234\nset default=0\nset timeout=0\n"+grub.render_entry(item))
        run('grub-mkstandalone','-O','x86_64-efi','-o',first,'boot/grub/grub.cfg='+str(start))
        run('mcopy','-o','-i',fat,first,'::/EFI/BOOT/BOOTX64.EFI')
        shutil.copyfile(vars_source,variables)
        boot(root,'Disconnected drive',['-drive',f'file={fat},format=raw'], 'The selected drive is not connected.',
             ['-drive',f'if=pflash,format=raw,readonly=on,file={ovmf}','-drive',f'if=pflash,format=raw,file={variables}'])
        # BIOS: load an independent Linux GRUB menu on another filesystem.
        tree=root/'linux';(tree/'boot/grub').mkdir(parents=True)
        (tree/'boot/grub/grub.cfg').write_text(SERIAL+'echo FUSION_LINUX_MENU_REACHED\nhalt\n')
        linux=root/'linux.img'
        with linux.open('wb') as stream:stream.truncate(64*1024*1024)
        fs_uuid='12121212-3434-5656-7878-909090909090'
        run('mke2fs','-q','-t','ext4','-U',fs_uuid,'-d',tree,linux)
        iso_root=root/'cd';(iso_root/'boot/grub').mkdir(parents=True)
        item.update(kind='config',uuid=fs_uuid,loader='/boot/grub/grub.cfg',filesystem='ext4',name='My Linux drive')
        item['id']=grub.entry_id(item)
        # The same independent Linux menu must also load from the UEFI editor.
        start.write_text(SERIAL+'set default=0\nset timeout=0\n'+grub.render_entry(item))
        run('grub-mkstandalone','-O','x86_64-efi','-o',first,'boot/grub/grub.cfg='+str(start))
        run('mcopy','-o','-i',fat,first,'::/EFI/BOOT/BOOTX64.EFI')
        shutil.copyfile(vars_source,variables)
        boot(root,'UEFI Linux menu',['-drive',f'file={fat},format=raw','-drive',f'file={linux},format=raw'],
             'FUSION_LINUX_MENU_REACHED',
             ['-drive',f'if=pflash,format=raw,readonly=on,file={ovmf}','-drive',f'if=pflash,format=raw,file={variables}'])
        # Exercise Current Grub's exact-range removal and command editing in
        # real GRUB, keeping the independently maintained target menu bootable.
        edited = SERIAL+'set default=0\nset timeout=0\n'+"menuentry 'Obsolete' { echo obsolete; halt; }\n"+grub.render_entry(item)
        edited = grub.edit_menu(edited, grub.menu_entries(edited)[0]['id'], remove=True)
        target_entry = grub.menu_entries(edited)[0]
        edited = grub.edit_menu(edited, target_entry['id'], name='Renamed Linux',
                                commands='echo FUSION_CURRENT_EDIT_APPLIED\n'+target_entry['commands'])
        start.write_text(edited); run('grub-script-check', start)
        run('grub-mkstandalone','-O','x86_64-efi','-o',first,'boot/grub/grub.cfg='+str(start))
        run('mcopy','-o','-i',fat,first,'::/EFI/BOOT/BOOTX64.EFI')
        shutil.copyfile(vars_source,variables)
        boot(root,'UEFI edited current menu',['-drive',f'file={fat},format=raw','-drive',f'file={linux},format=raw'],
             ['FUSION_CURRENT_EDIT_APPLIED', 'FUSION_LINUX_MENU_REACHED'],
             ['-drive',f'if=pflash,format=raw,readonly=on,file={ovmf}','-drive',f'if=pflash,format=raw,file={variables}'])
        (iso_root/'boot/grub/grub.cfg').write_text(edited)
        iso=root/'start.iso';run('grub-mkrescue','-d','/usr/lib/grub/i386-pc','-o',iso,iso_root)
        bios=next((Path(p) for p in ('/usr/share/qemu/bios-256k.bin','/usr/share/seabios/bios.bin') if Path(p).is_file()),None)
        boot(root,'BIOS edited current menu',['-cdrom',str(iso),'-boot','d','-drive',f'file={linux},format=raw'], ['FUSION_CURRENT_EDIT_APPLIED', 'FUSION_LINUX_MENU_REACHED'],
             ['-bios',str(bios)] if bios else [], qemu=shutil.which('qemu-system-i386'))


if __name__=='__main__':main()
