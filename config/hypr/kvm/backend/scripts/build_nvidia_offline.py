#!/usr/bin/env python3
"""Build a local NVIDIA installer disc from archived files. No network access."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "macos/NVIDIA-Offline"
VERSION = "2.5.3"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def offline_setup(source):
    """Change only support-kext fetching and the tested VM display-start flag."""
    start = source.index("fetch_kext() {")
    end = source.index("\nbooted_part()", start)
    local = '''# vmstart2: support kexts come from the verified local payload. No download fallback.
fetch_kext() {
  local k=$1 u s
  [ -n "$KT" ] || KT=$(mktemp -d) || stop "could not create a staging folder"
  read -r u s <<<"$(kurl $k)"
  [ -n "${NULLMOTH_OFFLINE_KEXTS:-}" ] && [ -f "$NULLMOTH_OFFLINE_KEXTS/$k.zip" ] || stop "offline support file missing: $k"
  cp "$NULLMOTH_OFFLINE_KEXTS/$k.zip" "$KT/$k.zip" || stop "could not stage $k"
  [ "$(shasum -a 256 "$KT/$k.zip" | awk '{print $1}')" = "$s" ] || stop "$k failed its pinned checksum"
  ditto -x -k "$KT/$k.zip" "$KT/$k.x" && [ -f "$KT/$k.x/$k/Contents/Info.plist" ] || stop "$k could not be unpacked"
}
'''
    source = source[:start] + local + source[end + 1:]
    line = re.search(r'^WANT_ARGS="[^"\n]+"$', source, re.M)
    if line is None or "-nvaccelnoheadless" in line.group():
        raise ValueError("Unexpected upstream boot-argument defaults; review before rebuilding")
    source = source[:line.end() - 1] + " -nvaccelnoheadless" + source[line.end() - 1:]
    return source


README = """vmstart2 — Offline NVIDIA setup 2.5.3

1. Install macOS and finish creating your account first.
2. In vmstart2 Mac & OpenCore, prepare the offline installer. It gives the
   guest a separate writable OpenCore copy and private NVRAM plus this disc.
3. Boot Single GPU or Dual GPU with one supported NVIDIA GPU passed through.
   Virtual GPU alone cannot provide NVIDIA acceleration.
4. Open this disc in Finder and double-click Install-NVIDIA.command.
   Enter your macOS administrator password, review the proposed changes,
   then type INSTALL. No internet connection is used by the installer.
5. Restart when requested. If security settings needed a first restart,
   setup resumes once on the next boot. Its log is under:
   /Library/Application Support/vmstart2/NVIDIA-2.5.3/State/install.log
   After files are installed, restart again. Allow extensions in macOS
   Privacy & Security if requested. Run Check-NVIDIA.command to verify Metal.

Supported: x86_64 macOS 15.5+ or 26.x, and cards in the bundled NVIDIA
Turing-or-newer device table. A listed card is not a guarantee that every
board, macOS update, display connection or passthrough configuration works.
The VM still needs correct CPU, firmware, PCI passthrough and USB settings.

RECOVERY
OpenCore includes '1401: Start once without NVIDIA driver' and '1401: Remove
NVIDIA driver'. The upstream installer keeps backups of changed components.
vmstart2 also keeps preset-before.json and the original host boot files.
Restoring a host preset only restores VM settings/boot paths, not guest OS
files. Keep an OS backup before driver upgrades. No automatic host reboot.

This disc contains the prebuilt driver, firmware, support kexts, recovery
tool, checksum manifest and a local wrapper around the upstream installer.
The original release and source repositories are archived on the Linux host
under macos/NVIDIA-Offline. Back up that entire directory, not just the ISO.

LICENSES / BUILDING
NullMoth's driver and 1401 use PolyForm Noncommercial 1.0.0; the translator
uses LGPL and other components have their own terms. See Runtime/Licenses
and the archived sources. This is source-available software, not a blanket
grant for commercial redistribution or use.
Offline installation uses the supplied binaries. A complete source rebuild
is not certified: Apple Xcode/SDK and every build tool are not bundled;
AMFIPass and vendor firmware are preserved as binary dependencies.
"""


def main():
    archive = json.loads((BUNDLE / "archive.json").read_text())
    if archive["version"] != VERSION:
        raise ValueError("Unexpected archive version")
    for relative, checksum in archive["files"].items():
        path = BUNDLE / relative
        if not path.resolve().is_relative_to(BUNDLE.resolve()) or path.is_symlink() or sha(path) != checksum:
            raise ValueError(f"Archive integrity check failed: {relative}")
    payload = BUNDLE / "Payloads" / VERSION
    output = BUNDLE / "Media"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".build-", dir=output) as temp:
        media = Path(temp) / "disc"
        runtime = media / "Runtime"
        runtime.mkdir(parents=True)
        for name in ("Install-NVIDIA.command", "Check-NVIDIA.command"):
            shutil.copyfile(ROOT / "macos/nvidia-installer" / name, media / name)
            (media / name).chmod(0o755)
        shutil.copyfile(ROOT / "macos/nvidia-installer/install-driver.sh", runtime / "install-driver.sh")
        shutil.copyfile(payload / "nullmoth-nvidia-2.5.3.tar.gz", runtime / "nullmoth-nvidia-2.5.3.tar.gz")
        shutil.copytree(payload / "Kexts", runtime / "Kexts")
        shutil.copytree(payload / "Licenses", runtime / "Licenses")
        original = (payload / "nullmoth-setup.sh").read_text()
        (runtime / "nullmoth-setup.offline.sh").write_text(offline_setup(original))
        (runtime / "upstream-setup.sh.txt").write_text(original)
        ids = json.loads((payload / "nvidia_gsp_ids.json").read_text())["ids"]
        if not ids or not all(re.fullmatch(r"[0-9A-F]{4}", key) for key in ids):
            raise ValueError("Invalid supported GPU table")
        (runtime / "supported-ids.txt").write_text("\n".join(sorted(ids)) + "\n")
        shutil.copyfile(payload / "nvidia_gsp_ids.json", runtime / "nvidia_gsp_ids.json")
        shutil.copyfile(payload / "nullmoth-rules.json", runtime / "upstream-rules.json")
        with zipfile.ZipFile(payload / "1401-Mac-2.5.3.zip") as zip_file:
            for name in ("NullMothSafe.efi", "nullmoth-metal-devices"):
                matches = [p for p in zip_file.namelist() if p.endswith("1401.app/Contents/Resources/" + name)]
                if len(matches) != 1:
                    raise ValueError(f"Expected one release helper: {name}")
                (runtime / name).write_bytes(zip_file.read(matches[0]))
                (runtime / name).chmod(0o755)
        for script in runtime.glob("*.sh"):
            script.chmod(0o755)
            subprocess.run(["bash", "-n", str(script)], check=True)
        hashes = {str(p.relative_to(runtime)): sha(p) for p in sorted(runtime.rglob("*")) if p.is_file()}
        (runtime / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in hashes.items()))
        (media / "READ-ME-FIRST.txt").write_text(README)
        all_files = {str(p.relative_to(media)): sha(p) for p in sorted(media.rglob("*")) if p.is_file()}
        identity = hashlib.sha256(json.dumps(all_files, sort_keys=True).encode()).hexdigest()[:12]
        final = output / f"vmstart2-NVIDIA-{VERSION}-{identity}.iso"
        temporary = Path(temp) / "installer.iso"
        subprocess.run(["xorriso", "-as", "mkisofs", "-quiet", "-r", "-J", "-joliet-long", "-iso-level", "3",
                        "-V", "VM2_NVIDIA", "-o", str(temporary), str(media)], check=True)
        checksum = sha(temporary)
        if final.exists():
            if sha(final) != checksum:
                # ISO timestamps can differ while contents match: keep the
                # existing verified image rather than overwrite attached media.
                old = json.loads((BUNDLE / "media.json").read_text())
                if old.get("files") != all_files or old.get("sha256") != sha(final):
                    raise ValueError("Existing media differs; refusing to replace it")
                checksum = old["sha256"]
        else:
            temporary.rename(final)
        report = dict(version=VERSION, iso=str(final.relative_to(BUNDLE)), sha256=checksum,
                      archive_sha256=sha(BUNDLE / "archive.json"), files=all_files)
        (BUNDLE / "media.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"Offline installer ready: {final}\nSHA-256: {checksum}")


if __name__ == "__main__":
    main()
