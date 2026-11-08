"""Public identities of modules authenticated and loaded during this boot.

The post-boot Windows helper must not look for plaintext .ko files. Record only
their ELF srcversions after a successful load, in root-owned volatile storage.
No image bytes, account tokens or decryption keys are stored here.
"""
import json
import os
from pathlib import Path
import platform
import re
import stat
import tempfile

RECEIPT = Path('/run/xetal-kvm-modules.json')
SYS_MODULE = Path('/sys/module')
BOOT_ID = Path('/proc/sys/kernel/random/boot_id')
MODULES = ('kvm', 'kvm_amd')
RESTART = ('Shut down the VM, enable the custom KVM module in Paths & Tools, '
           'then launch it again from KVM Settings on the matching AMD kernel.')


def check_loaded(record):
    if (not isinstance(record, dict) or record.get('schema') != 1
            or record.get('kernel') != platform.release()
            or record.get('boot_id') != BOOT_ID.read_text().strip()):
        raise RuntimeError('The custom module record is not for this boot. '+RESTART)
    versions = record.get('srcversions')
    if not isinstance(versions, dict) or set(versions) != set(MODULES):
        raise RuntimeError('Invalid custom module identities. '+RESTART)
    for name, expected in versions.items():
        if not isinstance(expected, str) or not re.fullmatch(r'[A-Fa-f0-9]{24}', expected):
            raise RuntimeError('Invalid custom module identity. '+RESTART)
        try:
            loaded = (SYS_MODULE/name/'srcversion').read_text().strip()
        except OSError:
            loaded = ''
        if loaded != expected:
            raise RuntimeError(f'The loaded {name} does not match the authenticated module. '+RESTART)
    if not (SYS_MODULE/'kvm_amd/parameters/intercept_cpuid').is_file():
        raise RuntimeError('The loaded KVM module does not provide native CPU timing. '+RESTART)
    return record


def record_loaded(kernel, srcversions):
    if os.geteuid() != 0:
        raise RuntimeError('Administrator access is required to record loaded KVM modules.')
    record = dict(schema=1, kernel=kernel, boot_id=BOOT_ID.read_text().strip(),
                  srcversions=srcversions)
    check_loaded(record)
    fd, temporary = tempfile.mkstemp(prefix='.xetal-kvm-modules-', dir=RECEIPT.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(record, stream)
            stream.write('\n')
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        os.replace(temporary, RECEIPT)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verified():
    try:
        fd = os.open(RECEIPT, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(fd, 'r') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                    or info.st_mode & 0o022 or info.st_size > 4096):
                raise ValueError('Untrusted module record')
            record = json.loads(stream.read(4097))
    except (OSError, ValueError) as error:
        raise RuntimeError('No verified custom-module load was recorded for this boot. '+RESTART) from error
    return check_loaded(record)
