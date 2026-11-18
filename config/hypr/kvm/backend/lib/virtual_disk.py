"""Create sparse raw guest disks or inspect existing images without changing them."""

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

GIB = 1024 ** 3
MAX_GIB = 16 * 1024


def image_path(directory, filename):
    directory, filename = str(directory).strip(), str(filename).strip()
    if not directory:
        raise ValueError("Choose a folder for the virtual disk.")
    if not filename or filename in (".", "..") or any(c in filename for c in "/\\\0\n\r"):
        raise ValueError("Enter a filename, without a folder path.")
    suffix = Path(filename).suffix.lower()
    if not suffix:
        filename += ".img"
    elif suffix not in (".img", ".raw"):
        raise ValueError("Use an .img or .raw filename for this disk.")
    folder = Path(directory).expanduser()
    if not folder.is_absolute():
        raise ValueError("Choose an absolute folder path.")
    return folder.resolve()/filename


def create_image(directory, filename, size_gib):
    """Return a new empty image; never truncate a pre-existing path or link."""
    if type(size_gib) is not int or not 1 <= size_gib <= MAX_GIB:
        raise ValueError(f"Choose a size between 1 and {MAX_GIB:,} GiB.")
    path = image_path(directory, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    except FileExistsError as error:
        raise ValueError("A file or folder with this name already exists. Choose another filename, "
                         "or select Use existing to attach this disk.") from error
    identity = os.fstat(fd)
    try:
        # Extending an empty raw image creates a hole rather than writing GiB
        # of zeros. QEMU's existing file block driver exposes these bytes.
        os.ftruncate(fd, size_gib * GIB)
        os.fsync(fd)
        current = path.lstat()
        if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
            raise RuntimeError("The destination changed while the disk was being created. Choose another filename.")
    except BaseException:
        # Remove only the incomplete file we created, not a replacement path.
        try:
            current = path.lstat()
            if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino) and stat.S_ISREG(current.st_mode):
                path.unlink()
        except FileNotFoundError:
            pass
        raise
    finally:
        os.close(fd)
    return path


def existing_image(filename, attached_paths=()):
    """Return a readable raw image, without creating, resizing or writing it."""
    filename = str(filename).strip()
    if not filename:
        raise ValueError("Choose an existing .img or .raw disk image.")
    path = Path(filename).expanduser()
    if not path.is_absolute():
        raise ValueError("Choose an absolute path to the disk image.")
    if path.suffix.lower() not in (".img", ".raw"):
        raise ValueError("Choose a raw .img or .raw disk image. Other image formats are not supported here.")
    path = path.resolve(strict=True)
    # NONBLOCK prevents a replaced path from hanging the worker on a FIFO.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Choose a disk image file, not a folder or physical device.")
        if info.st_size < 512:
            raise ValueError("The raw disk image must contain whole 512-byte sectors and cannot be empty.")
        for attached in attached_paths:
            try:
                other = os.stat(attached)
            except OSError:
                continue
            if (other.st_dev, other.st_ino) == (info.st_dev, info.st_ino):
                raise ValueError("This disk image is already active in this VM. Use its existing disk card.")
        header = os.pread(fd, 512, 0)
        footer = os.pread(fd, 512, info.st_size - 512)
        # The editor uses QEMU's raw file driver. Common container signatures
        # must not slip through just because a file was renamed to .img.
        if (header.startswith((b"QFI\xfb", b"QED\0", b"KDMV", b"COWD", b"vhdxfile", b"# Disk DescriptorFile"))
                or header[64:68] == b"\x7f\x10\xda\xbe"
                or header.startswith(b"conectix") or footer.startswith(b"conectix")):
            raise ValueError("This is not a raw disk image. Choose a raw .img or .raw file.")
        if info.st_size % 512:
            raise ValueError("The raw disk image must contain whole 512-byte sectors.")
        inspector = shutil.which("qemu-img")
        if inspector:
            result = subprocess.run([inspector, "info", "--output=json", str(path)],
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
            if result.returncode:
                raise ValueError("Could not inspect the disk image: " + (result.stderr.strip() or "qemu-img failed."))
            details = json.loads(result.stdout)
            if details.get("format") != "raw":
                raise ValueError("This is not a raw disk image. Choose a raw .img or .raw file.")
        current = path.stat()
        if (current.st_dev, current.st_ino, current.st_size) != (info.st_dev, info.st_ino, info.st_size):
            raise ValueError("The disk image changed while it was being checked. Select it again.")
    finally:
        os.close(fd)
    return path
