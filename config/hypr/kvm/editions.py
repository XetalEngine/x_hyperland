"""Edition selection changes managed tools, never a guest's disks or identity."""
from pathlib import Path
import json
import os

from edition_info import EDITIONS


def selected(root=None):
    from portable import data_root
    pinned=os.environ.get('XETAL_KVM_EDITION')
    if pinned in ('stock','xetallic'):return pinned
    try:
        value = json.loads(((root or data_root())/'edition.json').read_text())['edition']
    except (OSError, ValueError, KeyError):
        value = 'stock'
    return value if value in ('stock', 'xetallic') else 'stock'


def component_root(root=None, edition=None):
    from portable import data_root
    root = root or data_root()
    edition = edition or selected(root)
    if edition not in ('stock', 'xetallic'):
        raise ValueError('This VM edition is not available yet.')
    return root/'editions'/edition


def app_id(edition):
    return 'kvm-stock' if edition == 'stock' else 'kvm'


def select(edition, root=None):
    from portable import data_root
    from packages import atomic_json
    root = root or data_root()
    component_root(root, edition)
    atomic_json(root/'edition.json', {'edition': edition})


def apply(data, root=None, edition=None):
    """Remap managed paths, keeping user-supplied tools and writable state."""
    from portable import data_root, ROOT
    root = root or data_root()
    edition = edition or selected(root)
    destination = component_root(root, edition)/'components'
    old = data.get('_meta', {}).get('vm_edition')
    tools = data.setdefault('tools', {})
    if old is None and tools.get('kvm_build_enabled'):old='xetallic'
    if old in ('stock','xetallic') and old != edition:
        preferences=data.setdefault('edition_preferences', {})
        preferences[old]={'custom_module':bool(tools.get('kvm_build_enabled'))}
        tools['kvm_build_enabled']=(edition=='xetallic' and
            preferences.get(edition,{}).get('custom_module',False))
    prefixes = [root/'components', *(root/'editions'/key/'components' for key in ('stock', 'xetallic'))]
    def remap(value):
        if isinstance(value, dict): return {k:remap(v) for k,v in value.items()}
        if isinstance(value, list): return [remap(v) for v in value]
        if isinstance(value, str):
            for prefix in prefixes:
                if value.startswith(str(prefix)+'/'):
                    return str(destination)+value[len(str(prefix)):]
        return value
    changed = remap(data)
    data.clear(); data.update(changed)
    data.setdefault('_meta', {})['vm_edition'] = edition
    tools = data.setdefault('tools', {})
    if edition == 'stock':
        tools['kvm_build_enabled'] = False
    return data


def switch(data, edition, root=None):
    """Explicit edition selection uses that edition's QEMU and firmware pair."""
    from portable import data_root
    root = root or data_root()
    old = data.get('_meta', {}).get('vm_edition', selected(root))
    preferences = data.setdefault('edition_preferences', {})
    preferences[old] = {'custom_module': bool(data.get('tools', {}).get('kvm_build_enabled'))}
    apply(data, root, edition)
    base = component_root(root, edition)/'components'
    data['_meta']['binary'] = str(base/'qemu/current/bin/qemu-system-x86_64')
    # Only the read-only code flash is selected. NVRAM remains the guest's file.
    for block in data.get('blockdevs', []):
        if block.get('filename', '').endswith('/OVMF_CODE.fd'):
            block['filename'] = str(base/'ovmf/current/OVMF_CODE.fd')
    data['tools']['kvm_build_enabled'] = (edition == 'xetallic' and
        preferences.get(edition, {}).get('custom_module', False))
    select(edition, root)
