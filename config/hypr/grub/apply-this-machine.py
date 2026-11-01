#!/usr/bin/env python3
"""Manually enable the optional GRUB theme on this one inspected machine."""

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


BOOT = Path("/boot/grub")
CONFIG = BOOT / "grub.cfg"
SOURCE = Path(__file__).resolve().parent / "hyper-fusion"
DESTINATION = BOOT / "themes/hyper-fusion"
ROOT_UUID = "08dddc84-673e-4384-8d0b-c9de3aeb575b"
MARKER = "# Hyper Fusion theme (manual, machine-local)"
THEME_PATH = "($root)/boot/grub/themes/hyper-fusion"

BLOCK = f"""{MARKER}
search --no-floppy --fs-uuid --set=root {ROOT_UUID}
if loadfont ($root)/boot/grub/fonts/unicode.pf2; then
  set gfxmode=auto
  insmod all_video
  insmod gfxterm
  if terminal_output gfxterm; then
    insmod gfxmenu
    insmod png
    loadfont {THEME_PATH}/menu.pf2
    loadfont {THEME_PATH}/selected.pf2
    loadfont {THEME_PATH}/heading.pf2
    loadfont {THEME_PATH}/detail.pf2
    set theme={THEME_PATH}/theme.txt
    export theme
  fi
fi
# End Hyper Fusion theme
"""


def fail(message):
    raise SystemExit(message)


def main():
    if os.geteuid() != 0:
        fail("Run manually in your terminal with sudo python3 <this-script>.")
    if not SOURCE.is_dir() or not (SOURCE / "theme.txt").is_file():
        fail("Theme assets are missing beside this script.")
    if DESTINATION.exists():
        fail(f"{DESTINATION} already exists; inspect it before replacing anything.")
    if not CONFIG.is_file():
        fail(f"Cannot find {CONFIG}.")
    if not os.access(BOOT, os.W_OK):
        fail(f"{BOOT} is not writable in this terminal; no changes made.")
    old = CONFIG.read_text()
    if MARKER in old:
        fail("Theme marker already exists; no changes made.")
    if len(old) > 2048 or old.count("menuentry ") != 1:
        fail("GRUB config differs from the inspected single-entry menu; no changes made.")
    if not re.search(r"(?m)^set default=0$", old) or not re.search(r"(?m)^set timeout=5$", old):
        fail("Default or timeout changed since inspection; no changes made.")
    if not all(token in old for token in (ROOT_UUID, "linux /boot/xetal/vmlinuz-7.2.11-arch1-1", "initrd /boot/amd-ucode.img /boot/xetal/initramfs-7.2.11-arch1-1.img")):
        fail("Boot entry changed since inspection; no changes made.")
    if any(token in old for token in ("set theme=", "configfile ", "source ")):
        fail("Unexpected GRUB configuration found; no changes made.")
    required = ["theme.txt", "background.png", "menu.pf2", "selected.pf2", "heading.pf2", "detail.pf2"]
    required += [f"select_{part}.png" for part in ("nw", "n", "ne", "w", "c", "e", "sw", "s", "se")]
    missing = [name for name in required if not (SOURCE / name).is_file()]
    if missing:
        fail("Missing theme files: " + ", ".join(missing))
    for module in ("all_video", "gfxterm", "gfxmenu", "png"):
        if not (BOOT / f"x86_64-efi/{module}.mod").is_file():
            fail(f"GRUB module {module} is missing; no changes made.")

    candidate = old.replace("set timeout=5\n", "set timeout=5\n" + BLOCK, 1)
    if candidate.replace(BLOCK, "", 1) != old:
        fail("Could not preserve the original GRUB config; no changes made.")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".hyper-fusion-grub-", dir=BOOT)
    temporary = Path(temporary_name)
    stage = BOOT / "themes" / (".hyper-fusion-stage-" + str(os.getpid()))
    backup = BOOT / ("grub.cfg.pre-hyper-fusion-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(candidate)
            stream.flush()
            os.fsync(stream.fileno())
        subprocess.run(["grub-script-check", str(temporary)], check=True)
        shutil.copytree(SOURCE, stage)
        shutil.copy2(CONFIG, backup)
        os.chmod(backup, 0o600)
        stage.rename(DESTINATION)
        temporary.replace(CONFIG)
        print("Hyper Fusion GRUB theme enabled for this machine.")
        print("Original config backed up at: " + str(backup))
        print("Rollback: sudo cp " + str(backup) + " " + str(CONFIG))
        print("Reboot to verify the appearance; boot entry and timeout are unchanged.")
    finally:
        temporary.unlink(missing_ok=True)
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == "__main__":
    main()
