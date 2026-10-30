"""Update only OVMF's existing, unauthenticated display-resolution preference.

The store is validated by virt-firmware. We patch the eight display bytes in
place so boot entries, Secure Boot keys and all other firmware state are kept.
"""

import fcntl
import os
import stat
import struct
import uuid


PLATFORM_GUID = uuid.UUID("7235c51c-0c80-4cab-87ac-3b084a6304b1").bytes_le
PLATFORM_NAME = "PlatformConfig\0".encode("utf-16-le")


def available():
    try:
        from virt.firmware.varstore import edk2
        return True
    except ImportError:
        return False


def _resolution_offset(store):
    """Find the live OVMF variable in a validated authenticated EDK2 store."""
    data, pos, end = store.filedata, store.start, store.end
    if not (0 <= pos <= end <= len(data)):
        raise ValueError("Invalid OVMF variable-store bounds")
    found = None
    while pos + 60 <= end:
        if data[pos:pos + 2] == b"\xff\xff":
            break
        magic, state, attributes = struct.unpack_from("<HBxI", data, pos)
        name_size, value_size = struct.unpack_from("<II", data, pos + 36)
        value = pos + 60 + name_size
        if magic != 0x55aa or name_size < 2 or name_size % 2 or value + value_size > end:
            raise ValueError("Malformed OVMF variable; display preference was not changed")
        if (state == 0x3f and data[pos + 44:pos + 60] == PLATFORM_GUID
                and data[pos + 60:value] == PLATFORM_NAME):
            if attributes != 7 or value_size < 8 or found is not None:
                raise ValueError("Unsupported OVMF display variable; display preference was not changed")
            found = value
        pos = (value + value_size + 3) & ~3
    return found


def apply_resolution(path, width, height, backup):
    """Return the previous size if changed, or None if no override needs changing.

    Called before QEMU starts. POSIX record locking also conflicts with QEMU's
    block-file locks, so another running guest's firmware cannot be patched.
    """
    from virt.firmware.varstore import edk2

    if not (640 <= width <= 4096 and 480 <= height <= 4096):
        raise ValueError("Invalid firmware display size")
    with open(path, "r+b") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("The UEFI variable store must be a regular file")
        # Read before taking the lock: closing a second descriptor for the
        # same inode would drop POSIX locks. Recheck the bytes under lock.
        try:
            store = edk2.Edk2VarStore(path)
        except SystemExit as exc:
            raise ValueError("Unsupported UEFI variable store; disable Apply preferred size to UEFI") from exc
        fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if handle.read() != store.filedata:
            raise RuntimeError("UEFI variables changed during inspection; retry after shutting down other guests")
        offset = _resolution_offset(store)
        if offset is None:
            return None  # Without an override, OVMF can use the display's EDID.
        previous = store.filedata[offset:offset + 8]
        requested = struct.pack("<II", width, height)
        if previous == requested:
            return None
        # Keep an exact backup before touching the shared firmware file.
        with open(backup, "xb") as saved:
            os.fchmod(saved.fileno(), 0o600)
            saved.write(store.filedata)
            saved.flush()
            os.fsync(saved.fileno())
        try:
            handle.seek(offset)
            if handle.write(requested) != len(requested):
                raise OSError("Incomplete firmware display update")
            handle.flush()
            os.fsync(handle.fileno())
        except OSError:
            handle.seek(offset)
            handle.write(previous)
            handle.flush()
            os.fsync(handle.fileno())
            raise
        return struct.unpack("<II", previous)
