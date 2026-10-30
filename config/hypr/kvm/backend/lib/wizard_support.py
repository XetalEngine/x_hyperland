#!/usr/bin/env python3
"""Host-side changes the setup wizard needs to make, kept apart from the pure
enumeration in hostinfo.py because everything here can modify the machine.

The one genuinely privileged action is editing the kernel command line to turn
IOMMU on. That is done through the bootloader's own config plus its regenerate
step, with a backup taken first and the exact change shown to the user before it
runs. Nothing here executes on import; the wizard calls these explicitly.
"""

import os
import re
import shlex
import subprocess
import hashlib
from pathlib import Path


# --------------------------------------------------------------- bootloader ---
def detect_bootloader():
    """Which bootloader manages the kernel command line on this host.

    Returns a dict with 'kind' in {'grub', 'systemd-boot', 'unknown'} and the
    paths involved, so the wizard can edit the right file and run the right
    regenerate command instead of assuming GRUB everywhere.
    """
    if os.path.isfile("/etc/default/grub"):
        regen = "grub-mkconfig -o /boot/grub/grub.cfg"
        if os.path.isfile("/boot/grub2/grub.cfg"):        # Fedora/openSUSE layout
            regen = "grub-mkconfig -o /boot/grub2/grub.cfg"
        return {"kind": "grub", "config": "/etc/default/grub",
                "grub_cfg": shlex.split(regen)[-1], "regen": regen}

    entries = []
    for d in ("/boot/loader/entries", "/efi/loader/entries"):
        if os.path.isdir(d):
            entries = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".conf")]
            if entries:
                break
    if entries:
        return {"kind": "systemd-boot", "config": entries[0], "entries": entries,
                "regen": ""}

    return {"kind": "unknown", "config": "", "regen": ""}


def _grub_default_line(text):
    """The GRUB_CMDLINE_LINUX_DEFAULT assignment as (prefix, value, quote)."""
    m = re.search(r'^(GRUB_CMDLINE_LINUX_DEFAULT=)(["\'])(.*?)\2\s*$',
                  text, re.M)
    if not m:
        return None
    return m.group(1), m.group(3), m.group(2)


def read_cmdline(boot):
    """The command line the bootloader will apply on next boot.

    For GRUB that is GRUB_CMDLINE_LINUX_DEFAULT; for systemd-boot it is the
    'options' line of the first entry. Falls back to the live /proc/cmdline so
    the wizard always has something to show.
    """
    try:
        if boot["kind"] == "grub":
            parsed = _grub_default_line(open(boot["config"]).read())
            if parsed:
                return parsed[1]
        elif boot["kind"] == "systemd-boot":
            for line in open(boot["config"]):
                if line.startswith("options"):
                    return line.split(None, 1)[1].strip() if len(line.split(None, 1)) > 1 else ""
    except Exception:
        pass
    return live_cmdline()


def live_cmdline():
    try:
        return open("/proc/cmdline").read().strip()
    except Exception:
        return ""


# ------------------------------------------------------------------ planning ---
def plan_iommu_cmdline(vendor, current):
    """Compute the command line that turns IOMMU on for this vendor.

    Swaps any existing {intel,amd}_iommu token for the right one, guarantees
    iommu=pt (pass-through mode, which avoids the DMA-remapping overhead on host
    devices), and leaves every unrelated token exactly where it was. Returns
    (new_cmdline, list_of_change_descriptions).
    """
    want = "intel_iommu=on" if vendor == "intel" else "amd_iommu=on"
    other_key = "amd_iommu" if vendor == "intel" else "intel_iommu"

    tokens = current.split()
    changes = []
    out = []
    have_want = have_pt = False

    for tok in tokens:
        key = tok.split("=", 1)[0]
        if key == other_key:
            changes.append(f"remove '{tok}' (wrong CPU vendor)")
            continue
        if key in ("intel_iommu", "amd_iommu"):
            if tok == want:
                have_want = True
                out.append(tok)
            else:
                changes.append(f"change '{tok}' -> '{want}'")
                out.append(want)
                have_want = True
            continue
        if key == "iommu":
            have_pt = True
            if tok != "iommu=pt":
                changes.append(f"change '{tok}' -> 'iommu=pt'")
                out.append("iommu=pt")
            else:
                out.append(tok)
            continue
        out.append(tok)

    if not have_want:
        changes.append(f"add '{want}'")
        out.append(want)
    if not have_pt:
        changes.append("add 'iommu=pt'")
        out.append("iommu=pt")

    return " ".join(out), changes


def build_iommu_script(boot, new_cmdline):
    """A shell script that backs up the bootloader config, applies the new
    command line, and regenerates the boot config. Returned as text so the
    wizard can both show it and run it under sudo. Only GRUB is written
    automatically; other bootloaders return an empty script and the wizard
    prints manual instructions instead.
    """
    if boot["kind"] != "grub":
        return ""

    try:
        expected=hashlib.sha256(Path(boot['config']).read_bytes()).hexdigest()
    except OSError as error:
        return 'printf "%s\\n" '+shlex.quote(str(error))+' >&2; exit 1'
    argv=['python3',str(Path(__file__).with_name('iommu_edit.py')),
          '--config',boot['config'],'--boot-config',boot['grub_cfg'],
          '--expected',expected,'--cmdline',new_cmdline,'--',*shlex.split(boot['regen'])]
    return 'exec '+shlex.join(argv)


def apply_iommu_cmdline(boot, new_cmdline, timeout=180):
    """Run the IOMMU edit under sudo, returning (ok, combined_output).

    Follows the same passwordless-sudo assumption the Memory tab already makes
    for hugepage allocation. The caller is expected to have shown the diff and
    got confirmation first.
    """
    script = build_iommu_script(boot, new_cmdline)
    if not script:
        return False, "This bootloader is not edited automatically; see the manual steps."
    try:
        r = subprocess.run(["sudo", "bash", "-c", script],
                           capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode == 0, out.strip()
    except Exception as e:
        return False, f"failed to run the edit: {e}"


def manual_iommu_steps(boot, vendor, new_cmdline):
    """Human instructions for bootloaders we do not rewrite for the user."""
    if boot["kind"] == "systemd-boot":
        return ("systemd-boot detected. Edit the 'options' line of your boot entry:\n"
                f"  {boot.get('config', '/boot/loader/entries/*.conf')}\n"
                f"so it contains:\n  {new_cmdline}\n"
                "then reboot. No regenerate step is needed for systemd-boot.")
    return ("Could not identify the bootloader. Add these to your kernel command "
            f"line by hand and reboot:\n  {('intel_iommu=on' if vendor=='intel' else 'amd_iommu=on')} iommu=pt")
