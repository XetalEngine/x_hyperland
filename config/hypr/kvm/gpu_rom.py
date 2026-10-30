"""Read the PCI expansion ROM, using the Control Panel's sysfs approach."""
from datetime import datetime
from pathlib import Path
import os
import re
import subprocess
import sys
import uuid

LIMIT = 16 * 1024 * 1024
INSTRUCTIONS = ('The GPU may refuse ROM access while the desktop is using it. '
                'Open Control Panel → Device Manager, right-click this GPU and choose Dump vBIOS. '
                'If that also fails, dump it from a live USB or obtain the ROM for this exact card. '
                'Then choose that file with Browse beside ROM. The GPU was not detached or flashed.')


def device_path(slot):
    if not re.fullmatch(r'[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]', slot):
        raise ValueError('Invalid PCI address')
    return Path('/sys/bus/pci/devices') / slot.lower()


def read_rom(slot):
    device = device_path(slot)
    if int((device/'class').read_text(), 16) >> 16 != 3:
        raise ValueError('The selected PCI function is not a GPU')
    rom = device/'rom'
    try:
        rom.write_text('1')
        with rom.open('rb') as stream:
            data = stream.read(LIMIT + 1)
        if not data or len(data) > LIMIT:
            raise ValueError('The GPU returned an empty or oversized ROM')
        return data
    finally:
        # Restore ROM-read access even when the read fails. Never unbind/reset.
        if rom.exists(): rom.write_text('0')


def validated_image(data, vendor, device):
    """Keep a complete, matching PCI image chain, stripping any pre-header."""
    offset = 0
    while True:
        start = data.find(b'\x55\xaa', offset)
        if start < 0: break
        cursor = start; uefi = False; images = 0
        while cursor + 26 <= len(data) and images < 16:
            if data[cursor:cursor+2] != b'\x55\xaa': break
            pcir = cursor + int.from_bytes(data[cursor+24:cursor+26], 'little')
            if pcir < cursor+26 or pcir+22 > len(data) or data[pcir:pcir+4] != b'PCIR': break
            if int.from_bytes(data[pcir+4:pcir+6], 'little') != vendor: break
            if int.from_bytes(data[pcir+6:pcir+8], 'little') != device: break
            size = int.from_bytes(data[pcir+16:pcir+18], 'little') * 512
            if size < 512 or pcir+22 > cursor+size or cursor+size > len(data): break
            uefi |= data[pcir+20] == 3
            images += 1
            cursor += size
            if data[pcir+21] & 0x80:
                if not uefi: raise ValueError('The ROM has no UEFI GOP image for OVMF')
                return data[start:cursor]
        offset = start+2
    raise ValueError('The ROM is truncated, invalid, or belongs to another GPU')


def capture(slot):
    import portable
    from uiutil import sudo_command
    device = device_path(slot)
    vendor = int((device/'vendor').read_text(), 16)
    ident = int((device/'device').read_text(), 16)
    command, env, available = sudo_command([sys.executable, str(Path(__file__).resolve()), '--read', slot],
                                           'KVM Settings: read the selected GPU ROM')
    if not available: raise RuntimeError('Administrator password prompt is unavailable. '+INSTRUCTIONS)
    try:
        result = subprocess.run(command, env=env, capture_output=True, timeout=90)
        if result.returncode: raise RuntimeError(result.stderr.decode(errors='replace').strip())
        image = validated_image(result.stdout, vendor, ident)
    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as error:
        raise RuntimeError(str(error)+'\n\n'+INSTRUCTIONS) from error
    directory = portable.data_root()/'roms'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = f'gpu-{slot.replace(":", "-")}-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.rom'
    target = directory/name
    with target.open('xb') as stream: stream.write(image)
    target.chmod(0o600)
    return str(target)


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3 or sys.argv[1] != '--read' or os.geteuid() != 0:
            raise ValueError('This helper only reads a selected GPU ROM with administrator access')
        sys.stdout.buffer.write(read_rom(sys.argv[2]))
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
