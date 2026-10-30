#!/usr/bin/env python3
"""Explicit network-time preservation of the pinned, working NVIDIA release.

Runtime installation/building the ISO never calls this downloader. Mirrors have
complete objects (no partial clones); Cargo archives are checked against locks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "macos/NVIDIA-Offline"
VERSION = "2.5.3"
RELEASE = "https://github.com/nullmoth/nvidia-macos-driver/releases/download/v2.5.3/"
ARTIFACTS = {
    "nullmoth-nvidia-2.5.3.tar.gz": "6ec9d23f8d7e0ab340b9e0a9753f7c48722b9930118fff648d545e0b95016884",
    "1401-Mac-2.5.3.dmg": "361f7cf0ef7f84273ba730d5c14664962cae2304c310ae1a9e087f7bb0b4d9cb",
    "1401-Mac-2.5.3.zip": "90fcfb9c9d2812aed5b909153a91a91d4f3a4a2ce809aab028d05a8abc24b7ad",
    "1401-Mac-2.5.3.zip.sig": "96080ef230c7588311d2e85f8e3899a63d329d757bb8fb524b1d3952b41af127",
}
REPOS = (
    ("nvidia-macos-driver", "https://github.com/nullmoth/nvidia-macos-driver.git", "v2.5.3"),
    ("1401", "https://github.com/nullmoth/1401.git", "v2.5.3"),
    ("nvidia-open-kernel", "https://github.com/NVIDIA/open-gpu-kernel-modules.git", "615.78.08"),
    ("mesa", "https://gitlab.freedesktop.org/mesa/mesa.git", "17ca6174"),
    ("Lilu", "https://github.com/acidanthera/Lilu.git", "0515f40"),
    ("RestrictEvents", "https://github.com/acidanthera/RestrictEvents.git", "9265e78"),
    ("USBToolBox", "https://github.com/USBToolBox/kext.git", "1.2.0"),
    ("OpenCorePkg", "https://github.com/acidanthera/OpenCorePkg.git", "1.0.8"),
    ("VirtualSMC", "https://github.com/acidanthera/VirtualSMC.git", "1.3.8"),
    ("MacKernelSDK", "https://github.com/acidanthera/MacKernelSDK.git", "HEAD"),
    ("OpenCore-Legacy-Patcher", "https://github.com/dortania/OpenCore-Legacy-Patcher.git", "HEAD"),
)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(name, *args):
    return subprocess.check_output(["git", f"--git-dir={BUNDLE / 'Sources' / (name + '.git')}", *args])


def fetch(url, target, expected=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if expected and sha(target) != expected:
            raise ValueError(f"Existing file has the wrong checksum: {target}")
        return
    print("Preserving", target.name, flush=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "vmstart2-offline-archive"})
            with urllib.request.urlopen(request, timeout=180) as response:
                shutil.copyfileobj(response, stream)
            stream.close()
            if expected and sha(temporary) != expected:
                raise ValueError(f"Checksum mismatch: {url}")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


def preserve_notices(payload, records):
    notices = payload / "Licenses"
    notices.mkdir(exist_ok=True)
    extras = {"nvidia-macos-driver": ["translator/LICENSE", "translator/COPYING"],
              "mesa": ["licenses/MIT", "licenses/Apache-2.0", "licenses/BSL-1.0", "licenses/SGI-B-2.0"],
              "USBToolBox": ["README.md"]}
    for record in records:
        name, commit = record["name"], record["commit"]
        entries = git(name, "ls-tree", "--name-only", commit).decode().splitlines()
        paths = [p for p in entries if p.upper().startswith(("LICENSE", "COPYING", "NOTICE")) and p != "licenses"]
        for relative in paths + extras.get(name, []):
            (notices / (name + "-" + relative.replace("/", "-"))).write_bytes(git(name, "show", commit + ":" + relative))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="explicitly allow archive downloads")
    args = parser.parse_args()
    if not args.fetch:
        parser.error("Use --fetch to preserve upstream sources and release files; this is never needed to install from the finished bundle.")
    payload = BUNDLE / "Payloads" / VERSION
    payload.mkdir(parents=True, exist_ok=True)
    sources = BUNDLE / "Sources"
    sources.mkdir(exist_ok=True)
    for name, expected in ARTIFACTS.items():
        local = ROOT / "macos/GPU-diagnostics-20261023/Media" / name
        target = payload / name
        if not target.exists() and local.is_file() and sha(local) == expected:
            shutil.copyfile(local, target)
        fetch(RELEASE + name, target, expected)
    fetch(RELEASE + "SHA256SUMS.txt", payload / "upstream-SHA256SUMS.txt")
    fetch("https://api.github.com/repos/nullmoth/nvidia-macos-driver/releases/tags/v2.5.3", payload / "upstream-release.json")
    records = []
    old_lock = BUNDLE / "archive.json"
    pinned = {x["name"]: x["commit"] for x in json.loads(old_lock.read_text()).get("sources", [])} if old_lock.exists() else {}
    for name, url, ref in REPOS:
        path = sources / (name + ".git")
        print("Checking complete source mirror:", name, flush=True)
        if not path.exists():
            subprocess.run(["git", "clone", "--mirror", url, str(path)], check=True)
        if (path / "objects/info/alternates").exists() or list((path / "objects/pack").glob("*.promisor")) or (path / "shallow").exists():
            raise ValueError(f"Archive requires a self-contained full mirror: {path}")
        commit = git(name, "rev-parse", f"{pinned.get(name, ref)}^{{commit}}").decode().strip()
        # Mesa's historic tags contain a legacy date-spacing defect. Ignore that
        # formatting issue only; missing/corrupt objects still fail verification.
        git(name, "-c", "fsck.missingSpaceBeforeDate=ignore", "fsck", "--full", "--no-dangling")
        records.append(dict(name=name, url=url, ref=ref, commit=commit, path=str(path.relative_to(BUNDLE))))
    # The helper's pinned support downloads, used only if missing from the EFI.
    import re
    setup = git("1401", "show", "v2.5.3:mac/Resources/nullmoth-setup.sh").decode()
    for name, url, checksum in re.findall(r'(\w+\.kext)\) echo "(https://\S+) ([0-9a-f]{64})"', setup):
        fetch(url, payload / "Kexts" / (name + ".zip"), checksum)
    for relative in ("mac/Resources/nullmoth-setup.sh", "mac/Resources/nullmoth-rules.json", "mac/Resources/nvidia_gsp_ids.json"):
        (payload / Path(relative).name).write_bytes(git("1401", "show", "v2.5.3:" + relative))
    preserve_notices(payload, records)
    # Cargo's lockfiles pin content, not just moving registry URLs.
    crates = {}
    for name, relative in (("nvidia-macos-driver", "translator/translator/Cargo.lock"),
                           ("nvidia-macos-driver", "translator/wrapper/Cargo.lock"), ("1401", "mac/efi-safe/Cargo.lock")):
        lock = tomllib.loads(git(name, "show", "v2.5.3:" + relative).decode())
        for package in lock["package"]:
            if package.get("source", "").startswith("registry+"):
                filename = f"{package['name']}-{package['version']}.crate"
                url = f"https://static.crates.io/crates/{package['name']}/{filename}"
                fetch(url, sources / "crates" / filename, package["checksum"])
                crates[filename] = dict(sha256=package["checksum"], url=url)
            elif package.get("source", "").startswith("git+"):
                raise ValueError(f"Unarchived Cargo git dependency: {package}")
    files = {str(path.relative_to(BUNDLE)): sha(path) for path in payload.rglob("*") if path.is_file()}
    report = dict(version=VERSION, sources=records, crates=crates, files=files,
                  installation="All runtime payloads are local; guest installer networking is denied.",
                  source_build="Upstream sources and locked Rust crates are archived. A complete offline source rebuild is NOT certified: Apple's Xcode/SDK and all build tools are not included; AMFIPass and vendor firmware are preserved as binaries.")
    old_lock.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Archived {len(records)} complete source mirrors, {len(crates)} locked crates and {len(files)} payload files.", flush=True)


if __name__ == "__main__":
    main()
