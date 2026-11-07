"""Read-only selection of the optional published module for this running host.

The saved checkbox expresses a preference, never a promise that a particular
kernel can load the package. Re-evaluate at each launch; do not save fallback.
"""
from pathlib import Path
import platform
import editions
import packages
import portable


def managed(data):
    path = data.get('tools', {}).get('kvm_build', '')
    return bool(path) and Path(path).resolve() == portable.ROOT / 'module-tool.sh'


def requested(data):
    return (managed(data) and data.get('_meta', {}).get('vm_edition', editions.selected()) == 'xetallic'
            and bool(data.get('tools', {}).get('kvm_build_enabled')))


def busy_reason():
    try:
        rows = [line.split() for line in Path('/proc/modules').read_text().splitlines()]
        for row in rows:
            if len(row) < 4:
                continue
            if row[0] in ('kvm_amd', 'kvm_intel') and int(row[2]):
                return 'Another VM is using KVM; the loaded module will be kept'
            # kvm_amd depending on kvm is normal, not an active VM.
            if row[0] == 'kvm' and (int(row[2]) > len([x for x in row[3].split(',') if x not in ('', '-')])
                                  or any(x not in ('', '-', 'kvm_amd', 'kvm_intel') for x in row[3].split(','))):
                return 'Another KVM consumer prevents a module reload; the loaded module will be kept'
    except (OSError, ValueError):
        return 'KVM module usage could not be checked'
    return ''


def unavailable(directory=None, *, check_busy=True):
    base = editions.component_root(directory)
    try:
        entry = packages.installed('kvm-amd', base)
        if not entry:
            return 'No custom KVM module is installed for this running kernel'
        reason = packages.compatibility('kvm-amd', entry)
        if reason:
            return reason
        path = base / 'components/kvm-amd/current'
        files = ['load-kvm.sh']
        if entry.get('runtime'):
            files += ['.vm-runtime.json', *(v['file'] for v in entry['runtime']['files'].values())]
        else:
            files += ['kvm.ko', 'kvm-amd.ko']
        if any(not (path / name).is_file() for name in files):
            return 'The optional custom KVM module download is incomplete'
    except (OSError, ValueError, KeyError, TypeError):
        return 'The optional custom KVM module metadata cannot be read'
    return busy_reason() if check_busy else ''


def warning(data, release=None):
    if not requested(data):
        return '', ''
    reason = unavailable()
    if not reason:
        return '', ''
    entry = (release or {}).get('components', {}).get('kvm-amd', {})
    kernel = platform.release()
    text = f'⚠ Kernel {kernel}: KVM interception / native timing tweaks unavailable. Using standard KVM.'
    if 'using KVM' in reason or 'consumer' in reason:
        text = '⚠ KVM is in use. Keeping the loaded module; custom interception / timing changes are skipped.'
    elif entry and not packages.compatibility('kvm-amd',entry):
        text = f'Kernel {kernel} is compatible. Its KVM interception module still needs to be prepared.'
    detail = reason + '. VM launch continues automatically. Your custom-module preference is kept.'
    if entry.get('kernel') and entry['kernel'] != kernel:
        detail += '\nPublished build: AMD · kernel ' + entry['kernel'] + '. Boot that kernel to use it.'
    detail += '\nA matching download is prepared when Settings opens. Modules are loaded only when you launch a VM.'
    return text, detail
