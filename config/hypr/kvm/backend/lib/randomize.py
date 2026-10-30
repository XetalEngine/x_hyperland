#!/usr/bin/env python3
"""Random identity generation for vmstart_2.

Serials and SMBIOS strings are fixed-width fields in structures that were
already laid out, so a replacement has to be exactly as long as what it
replaces. These helpers preserve length, and preserve shape: a digit stays a
digit, a letter stays a letter, and separators stay where they are.
"""

import random
import string
import uuid


def like(text):
    """A random string with the same length and character shape as `text`.

    'A792S370O3' -> 'K315V904P8'; '209777555891' -> '481203996714';
    'SRD\\x00MS-3C96F' keeps the NUL and the hyphen exactly where they were.
    Anything that is not a letter or digit is copied through untouched,
    because in SMBIOS those bytes are usually structure, not content.
    """
    out = []
    for ch in text:
        if ch.isdigit():
            out.append(random.choice(string.digits))
        elif ch.isupper():
            out.append(random.choice(string.ascii_uppercase))
        elif ch.islower():
            out.append(random.choice(string.ascii_lowercase))
        else:
            out.append(ch)
    return "".join(out)


def serial(n=12, alphabet=None):
    """A fresh device serial.

    Uppercase alphanumeric by default, which is what every real disk reports.
    """
    alphabet = alphabet or (string.ascii_uppercase + string.digits)
    return "".join(random.choice(alphabet) for _ in range(n))


def uuid4():
    """A random SMBIOS System UUID, upper case as dmidecode prints it."""
    return str(uuid.uuid4()).upper()


def hex_of(text):
    """Latin-1 hex encoding, matching how the patch table stores its bytes."""
    return text.encode("latin-1", errors="replace").hex()
