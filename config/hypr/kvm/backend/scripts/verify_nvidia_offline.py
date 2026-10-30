#!/usr/bin/env python3
"""Verify an existing NVIDIA archive without accessing the network."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "macos/NVIDIA-Offline"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked(root, relative, digest):
    path = root / relative
    if (not relative or Path(relative).is_absolute() or not path.resolve().is_relative_to(root.resolve())
            or path.is_symlink() or not path.is_file() or sha(path) != digest):
        raise ValueError(f"Missing or altered archive file: {relative}")
    return path


def verify(bundle, sources=False, contents=False):
    archive = json.loads((bundle / "archive.json").read_text())
    media = json.loads((bundle / "media.json").read_text())
    checked(bundle, "archive.json", media["archive_sha256"])
    for relative, digest in archive["files"].items():
        checked(bundle, relative, digest)
    for name, record in archive["crates"].items():
        checked(bundle, "Sources/crates/" + name, record["sha256"])
    iso = checked(bundle, media["iso"], media["sha256"])
    print(f"Verified {len(archive['files'])} payload files, {len(archive['crates'])} Rust archives and the installer ISO.", flush=True)
    if contents:
        with tempfile.TemporaryDirectory(prefix="vmstart2-nvidia-verify-") as temp:
            tree = Path(temp) / "disc"
            result = subprocess.run(["xorriso", "-osirrox", "on", "-indev", str(iso), "-extract", "/", str(tree)],
                                    capture_output=True, text=True, timeout=120)
            if result.returncode:
                raise ValueError("Cannot extract installer disc: " + result.stderr[-1500:])
            for relative, digest in media["files"].items():
                checked(tree, relative, digest)
            actual = {str(p.relative_to(tree)) for p in tree.rglob("*") if p.is_file()}
            if actual != set(media["files"]):
                raise ValueError("The installer disc contains unexpected files.")
            print(f"Read back and verified all {len(actual)} files from the ISO.", flush=True)
    if sources:
        for record in archive["sources"]:
            repository = bundle / record["path"]
            if (repository.is_symlink() or not repository.resolve().is_relative_to(bundle.resolve())
                    or not repository.is_dir() or (repository / "shallow").exists()
                    or (repository / "objects/info/alternates").exists()
                    or list((repository / "objects/pack").glob("*.promisor"))):
                raise ValueError("Not a complete self-contained source mirror: " + record["name"])
            env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
            git = ["git", f"--git-dir={repository}"]
            subprocess.run(git + ["cat-file", "-e", record["commit"] + "^{commit}"], env=env, check=True)
            subprocess.run(git + ["-c", "fsck.missingSpaceBeforeDate=ignore", "fsck", "--full", "--no-dangling"],
                           env=env, check=True, stdout=subprocess.DEVNULL)
            print("Verified complete source mirror: " + record["name"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", action="store_true", help="also verify every source-repository object (slower)")
    parser.add_argument("--contents", action="store_true", help="also extract and verify every file on the ISO")
    args = parser.parse_args()
    verify(BUNDLE, args.sources, args.contents)


if __name__ == "__main__":
    main()
