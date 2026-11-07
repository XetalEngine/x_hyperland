#!/usr/bin/env python3
"""Refresh supported IDs from the installed, signed NVIDIA package at each build."""
from pathlib import Path
import re
import sys


def device_ids(html):
    try:
        section = html.split('<h3>Current NVIDIA GPUs</h3>', 1)[1].split('</tbody>', 1)[0]
    except IndexError as error:
        raise ValueError('The installed NVIDIA supported-device table has changed; review it before rebuilding the boot image.') from error
    ids = sorted({'0x'+value.lower() for value in re.findall(r'<tr id="devid([0-9A-Fa-f]{4})', section)})
    if not ids: raise ValueError('The installed NVIDIA package has no readable supported-device table.')
    return ids


if __name__ == '__main__':
    source = Path('/usr/share/doc/nvidia/html/supportedchips.html')
    destination = Path('/etc/hyperfusion/graphics/nvidia-supported.txt')
    values = device_ids(source.read_text())
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    temporary.write_text('\n'.join(values)+'\n');temporary.chmod(0o644)
    temporary.replace(destination)
