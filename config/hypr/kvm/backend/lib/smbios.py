#!/usr/bin/env python3
"""SMBIOS blob preparation for vmstart_2.

Replaces the ReplaceBiosFile / ReplaceBytes / SetSmbiosUuid shell functions so
vmstart_2 does not depend on ~/.zshrc. The pristine dump is never modified: it
is copied to the output blob first, then patched there, exactly as win10_vm
does it.

Order matters. The UUID is written last so a byte pattern cannot land inside
the Type 1 UUID field and corrupt it.
"""

import json
import os
import shutil
import uuid as _uuid


class SmbiosError(Exception):
    pass


def blob_path(option):
    """Return the file= value, or None for QEMU's inline type= options.

    QEMU escapes literal commas in option values by doubling them. An empty
    file= remains an empty path so preflight can report it as missing.
    """
    for part in str(option or "").replace(",,", "\0").split(","):
        key, separator, value = part.partition("=")
        if separator and key == "file":
            return value.replace("\0", ",")
    return None


def load_config(path):
    with open(path) as f:
        return json.load(f)


# ------------------------------------------------------------- structures ---
def iter_structures(data):
    """Yield (type, offset, length) for each SMBIOS structure."""
    off = 0
    if data[:5] == b"_SM3_":
        off = data[6]
    elif data[:4] == b"_SM_":
        off = data[5]
    # Dumps often pad between the entry point and the first structure; walk to
    # the first plausible header instead of trusting the declared length.
    while off + 4 <= len(data) and not (data[off + 1] >= 4 and data[off] <= 127):
        off += 1
    p = off
    while p + 4 <= len(data):
        stype, slen = data[p], data[p + 1]
        if slen < 4:
            break
        q = p + slen
        while q + 1 < len(data) and not (data[q] == 0 and data[q + 1] == 0):
            q += 1
        yield stype, p, slen
        if stype == 127:
            break
        p = q + 2


# Type 0 (BIOS Information) fields the UI can edit. The three string fields are
# referenced from the formatted area by 1-based index into the structure's own
# string table, so their length is free to change; the two release bytes live at
# fixed offsets inside the formatted area.
TYPE0_STRING_FIELDS = [
    ("vendor",  0x04, "Vendor"),
    ("version", 0x05, "BIOS Version"),
    ("date",    0x08, "BIOS Release Date"),
]
TYPE0_BYTE_FIELDS = [
    ("release_major", 0x14, "System BIOS Major Release"),
    ("release_minor", 0x15, "System BIOS Minor Release"),
]


def entry_point_len(data):
    """Bytes of SMBIOS entry point at the head of a dump, or 0 if there is none.

    A dump taken from a running machine starts with an _SM_/_SM3_ anchor. QEMU's
    '-smbios file=' wants raw structure-table bytes and blindly reads the first
    two bytes as a structure header, so an anchor left in place is parsed as a
    bogus structure and eats whatever follows it.
    """
    if data[:5] == b"_SM3_":
        return int.from_bytes(data[0x10:0x18], "little") or data[6]
    if data[:4] == b"_SM_":
        return int.from_bytes(data[0x18:0x1C], "little") or data[5]
    return 0


def _walk(data, start=0):
    """Yield (type, off, length, end) for a raw structure table."""
    p = start
    while p + 4 <= len(data):
        stype, slen = data[p], data[p + 1]
        if slen < 4:
            return
        q = p + slen
        if q + 1 < len(data) and data[q] == 0 and data[q + 1] == 0:
            q += 2                      # no strings: bare double NUL
        else:
            while q < len(data):
                e = data.find(b"\x00", q)
                if e < 0:
                    q = len(data)
                    break
                if e == q:              # empty string closes the list
                    q = e + 1
                    break
                q = e + 1
        yield stype, p, slen, q
        if stype == 127:
            return
        p = q


def _strings_of(data, off, slen, end):
    raw = bytes(data[off + slen:end])
    return [s.decode("latin1") for s in raw.split(b"\x00") if s]


def read_type0(data, start=0):
    """Current Type 0 values, or {} when the table has no Type 0."""
    for stype, off, slen, end in _walk(data, start):
        if stype != 0:
            continue
        strs = _strings_of(data, off, slen, end)
        out = {}
        for key, pos, _label in TYPE0_STRING_FIELDS:
            if pos < slen:
                i = data[off + pos]
                out[key] = strs[i - 1] if 0 < i <= len(strs) else ""
        for key, pos, _label in TYPE0_BYTE_FIELDS:
            out[key] = data[off + pos] if pos < slen else 0
        return out
    return {}


def _set_type0(data, want):
    """Rewrite Type 0's strings and release bytes. Returns (new_data, log).

    Strings may change length: nothing in SMBIOS refers to a structure by byte
    offset, so re-serialising the table around a longer string is safe.
    """
    log = []
    for stype, off, slen, end in _walk(data, 0):
        if stype != 0:
            continue
        strs = _strings_of(data, off, slen, end)
        head = bytearray(data[off:off + slen])

        for key, pos, label in TYPE0_STRING_FIELDS:
            v = want.get(key)
            if v is None or v == "" or pos >= slen:
                continue
            idx = head[pos]
            if idx == 0:                      # field was unset: append a string
                strs.append(v)
                head[pos] = len(strs)
                log.append(f"ok    {label:22} (unset) -> {v}")
            else:
                old = strs[idx - 1] if idx <= len(strs) else ""
                if old == v:
                    continue
                while len(strs) < idx:
                    strs.append("")
                strs[idx - 1] = v
                log.append(f"ok    {label:22} {old} -> {v}")

        for key, pos, label in TYPE0_BYTE_FIELDS:
            v = want.get(key)
            if v is None or v == "" or pos >= slen:
                continue
            n = int(v) & 0xFF
            if head[pos] != n:
                log.append(f"ok    {label:22} {head[pos]} -> {n}")
                head[pos] = n

        tail = b"".join(s.encode("latin1") + b"\x00" for s in strs)
        tail = (tail + b"\x00") if strs else b"\x00\x00"
        return bytearray(bytes(data[:off]) + bytes(head) + tail + bytes(data[end:])), log
    log.append("WARN  no Type 0 (BIOS Information) structure to edit")
    return data, log


def find_type1_uuid_offset(data):
    for stype, off, slen in iter_structures(data):
        if stype == 1:
            if slen < 24:
                raise SmbiosError(f"Type 1 at 0x{off:x} too short ({slen}) for a UUID")
            return off + 8
    raise SmbiosError("no Type 1 (System Information) structure found")


def read_uuid(path):
    data = open(path, "rb").read()
    off = find_type1_uuid_offset(data)
    return str(_uuid.UUID(bytes_le=bytes(data[off:off + 16])))


# ------------------------------------------------------------------ apply ---
def apply(cfg, dry_run=False):
    """Build the output blob from the template. Returns a list of log lines."""
    log = []
    tpl, out = cfg["template_blob"], cfg["output_blob"]

    if not os.path.isfile(tpl):
        raise SmbiosError(f"template blob missing: {tpl}")
    if os.path.abspath(tpl) == os.path.abspath(out):
        raise SmbiosError("output blob must differ from the template; "
                          "the pristine dump must never be written to")

    if dry_run:
        data = bytearray(open(tpl, "rb").read())
        log.append(f"[dry-run] would copy {tpl} -> {out}")
    else:
        shutil.copyfile(tpl, out)
        data = bytearray(open(out, "rb").read())
        log.append(f"copied {tpl} -> {out} ({len(data)} bytes)")

    # Drop the dump's entry point before anything else. QEMU appends this file
    # to the guest's structure table verbatim and reads byte 0 as a structure
    # type, so a surviving _SM3_ anchor is parsed as a 83-byte "type 95" record
    # that swallows the real Type 0 behind it -- the guest then sees no BIOS
    # Information structure at all.
    ep = entry_point_len(data)
    if ep:
        del data[:ep]
        log.append(f"stripped {ep}-byte SMBIOS entry point; QEMU wants the raw "
                   f"structure table ({len(data)} bytes remain)")

    original_len = len(data)

    for p in cfg.get("patches", []):
        if not p.get("enabled", True):
            log.append(f"skip (disabled): {p.get('label','')}")
            continue
        find = bytes.fromhex(p["find_hex"])
        repl = bytes.fromhex(p["replace_hex"])
        if len(find) != len(repl):
            raise SmbiosError(
                f"{p.get('label','patch')}: replacement is {len(repl)} bytes but "
                f"pattern is {len(find)}; SMBIOS strings are fixed width")
        idx = data.find(find)
        if idx < 0:
            log.append(f"WARN  {p.get('label','patch')}: pattern not found "
                       f"({p.get('find_ascii','')})")
            continue
        if data.find(find, idx + 1) >= 0:
            log.append(f"WARN  {p.get('label','patch')}: pattern occurs more than "
                       f"once, patching the first at 0x{idx:x}")
        data[idx:idx + len(find)] = repl
        log.append(f"ok    {p.get('label','patch'):22} @ 0x{idx:<5x} "
                   f"{p.get('find_ascii','')} -> {p.get('replace_ascii','')}")

    # Byte patches are fixed width by contract; catch a bug here rather than
    # writing a table whose structures no longer line up.
    if len(data) != original_len:
        raise SmbiosError("a byte patch changed the blob size; refusing to write")

    # Type 0 next: it may lengthen a string and shift everything after it, so it
    # has to finish before the Type 1 UUID offset is looked up below.
    t0 = {k: v for k, v in (cfg.get("type0") or {}).items()
          if v is not None and str(v) != ""}
    if t0:
        data, t0log = _set_type0(data, t0)
        log.extend(t0log)
        original_len = len(data)

    want = cfg.get("system_uuid", "").strip()
    if want:
        off = find_type1_uuid_offset(data)
        before = str(_uuid.UUID(bytes_le=bytes(data[off:off + 16])))
        data[off:off + 16] = _uuid.UUID(want).bytes_le
        log.append(f"ok    {'System UUID':22} @ 0x{off:<5x} {before} -> {want.lower()}")

    if len(data) != original_len:
        raise SmbiosError("blob size changed; refusing to write")

    if not dry_run:
        with open(out, "wb") as f:
            f.write(bytes(data))
        # Read back rather than trusting the write.
        check = open(out, "rb").read()
        if len(check) != original_len:
            raise SmbiosError("verify failed: size mismatch after write")
        if want and str(_uuid.UUID(bytes_le=check[off:off + 16])) != want.lower():
            raise SmbiosError("verify failed: UUID did not take")
        log.append(f"verified {out}")

    return log


if __name__ == "__main__":
    import sys
    cfg = load_config(sys.argv[1])
    if len(sys.argv) > 2:
        cfg["output_blob"] = sys.argv[2]
    for line in apply(cfg, dry_run="--dry-run" in sys.argv):
        print("  " + line)
