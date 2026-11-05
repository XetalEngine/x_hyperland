#!/usr/bin/env python3
"""Boot the appearance renderer in disposable UEFI/BIOS guests, never host disks."""
import argparse
import base64
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from PIL import Image
import grub_appearance as appearance


def run(*args):
    result = subprocess.run(list(map(str, args)), capture_output=True, timeout=90)
    if result.returncode: raise RuntimeError(result.stderr.decode(errors='replace')[-3000:])


def wait(predicate, seconds=35):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(.1)
    raise RuntimeError('Disposable GRUB guest timed out.')


def boot(directory, name, args, picture=True, bios=False):
    serial = directory/(name+'.serial'); errors = directory/(name+'.errors')
    with errors.open('wb') as log:
        executable = shutil.which('qemu-system-i386' if bios else 'qemu-system-x86_64')
        firmware = ['-bios', '/usr/share/qemu/bios-256k.bin'] if bios else []
        process = subprocess.Popen([executable, '-no-user-config',
            '-machine', 'q35,accel=tcg', '-m', '256', '-vga', 'std', '-display', 'none',
            '-monitor', 'stdio', '-serial', 'file:'+str(serial), '-parallel', 'none',
            '-nic', 'none', '-no-reboot', *firmware, *args], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
        def output(): return serial.read_text(errors='replace') if serial.exists() else ''
        try:
            wait(lambda: 'FUSION_APPEARANCE_READY' in output())
            time.sleep(2)
            screenshot = directory/(name+'.ppm')
            process.stdin.write(('screendump '+str(screenshot)+'\n').encode()); process.stdin.flush()
            wait(screenshot.exists, 5)
            with Image.open(screenshot) as image:
                image.save(directory/(name+'.png'))
                if picture:
                    # A black console cannot pass the colored-background check.
                    colors = image.convert('RGB').getcolors(image.width*image.height)
                    assert len(colors) > 500, 'Theme artwork did not render'
            process.stdin.write(b'sendkey ret\n'); process.stdin.flush()
            wait(lambda: 'FUSION_APPEARANCE_BOOT_OK' in output())
            assert 'FUSION_ROOT_PRESERVED' in output(), output()
            assert 'error:' not in output().lower(), output()
            print('PASS:', name, 'theme, existing entry and root preserved', flush=True)
        finally:
            if process.poll() is None: process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('output', type=Path); args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='fusion-grub-visual-') as temporary:
        root = Path(temporary); art = root/'design'; art.mkdir()
        options = {**appearance.presets()[2]['options'], 'heading': 'HOLLOW GROVE'}
        prepared = appearance.prepare(options)
        for name, data in prepared['files'].items(): (art/name).write_bytes(base64.b64decode(data))
        (art/'theme.txt').write_text(appearance.theme_text(options))
        fat = root/'boot.img'
        with fat.open('wb') as stream: stream.truncate(128*1024*1024)
        run('mkfs.fat', '-F', '32', '-i', 'CABF1234', fat)
        run('mmd', '-i', fat, '::/EFI', '::/EFI/BOOT', '::/boot', '::/boot/grub', '::/boot/grub/themes')
        run('mcopy', '-s', '-i', fat, art, '::/boot/grub/themes/design')
        block = appearance.appearance_block('CABF-1234', '/boot/grub/themes/design')
        config = '''serial --unit=0 --speed=115200
terminal_output console serial
search --fs-uuid --set=root CABF-1234
set fusion_test_original_root=$root
set default=0
set timeout=60
menuentry 'Start my Linux system' {
  terminal_output console serial
  if [ "$root" = "$fusion_test_original_root" ]; then echo FUSION_ROOT_PRESERVED; fi
  echo FUSION_APPEARANCE_BOOT_OK
  halt
}
menuentry 'Advanced options' { halt; }
menuentry 'UEFI Firmware Settings' { halt; }
'''+block+'''terminal_output --append serial
echo FUSION_APPEARANCE_READY
'''
        source = root/'grub.cfg'; source.write_text(config); run('grub-script-check', source)
        efi = root/'bootx64.efi'; run('grub-mkstandalone', '-O', 'x86_64-efi', '-o', efi, 'boot/grub/grub.cfg='+str(source))
        run('mcopy', '-i', fat, efi, '::/EFI/BOOT/BOOTX64.EFI')
        ovmf = next(Path(p) for p in ('/usr/share/OVMF/OVMF_CODE.fd', '/usr/share/edk2/x64/OVMF_CODE.4m.fd') if Path(p).is_file())
        variables = root/'vars.fd'; shutil.copyfile(ovmf.with_name(ovmf.name.replace('CODE', 'VARS')), variables)
        boot(args.output, 'uefi', ['-drive', f'if=pflash,format=raw,readonly=on,file={ovmf}',
             '-drive', f'if=pflash,format=raw,file={variables}', '-drive', f'file={fat},format=raw'])
        iso_root = root/'cd'; (iso_root/'boot/grub').mkdir(parents=True)
        (iso_root/'boot/grub/grub.cfg').write_text(config)
        iso = root/'grub.iso'; run('grub-mkrescue', '-d', '/usr/lib/grub/i386-pc', '-o', iso, iso_root)
        boot(args.output, 'bios', ['-cdrom', str(iso), '-boot', 'd', '-drive', f'file={fat},format=raw'], bios=True)
        # Missing assets skip presentation and preserve the usable boot menu.
        (iso_root/'boot/grub/grub.cfg').write_text(config.replace('/themes/design/', '/themes/missing/'))
        run('grub-mkrescue', '-d', '/usr/lib/grub/i386-pc', '-o', iso, iso_root)
        boot(args.output, 'fallback', ['-cdrom', str(iso), '-boot', 'd', '-drive', f'file={fat},format=raw'], picture=False, bios=True)
        print('GRUB APPEARANCE BOOT CHECKS PASSED', flush=True)


if __name__ == '__main__': main()
