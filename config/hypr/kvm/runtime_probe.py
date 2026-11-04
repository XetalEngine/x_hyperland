"""Read QEMU capabilities in a launch session, without guest disks or modules."""
from pathlib import Path
import json
import os
import sys

import portable


def resident():
    if os.geteuid()!=0 or not os.environ.get('XETAL_KVM_LAUNCH_SOCKET'):
        raise RuntimeError('Start the device check from KVM Settings.')
    sys.path.insert(0,str(portable.ROOT/'backend/lib'))
    import virtual_gpu,dual_gpu
    binary=str(portable.component_path('qemu')/'bin/qemu-system-x86_64')
    caps=virtual_gpu.capabilities(binary)
    if not caps['devices']:raise RuntimeError('Could not inspect the selected QEMU build.')
    result={'capabilities':dict(caps,devices=sorted(caps['devices'])),'guest_device_ids':{},'ivshmem_ids':{},'errors':{}}
    for name,probe in [('guest_device_ids',virtual_gpu.guest_device_ids),('ivshmem_ids',dual_gpu.ivshmem_ids)]:
        if name=='ivshmem_ids' and 'ivshmem-plain' not in caps['devices']:continue
        try:result[name]=probe(binary)
        except Exception as error:result['errors'][name]=str(error)
    print(json.dumps(result))


def main():
    if sys.argv[1:]==['--resident']:resident();return 0
    if sys.argv[1:]:raise ValueError('Unexpected device check arguments.')
    import vm_session
    # Keep the short-lived launch authorization for the user's subsequent VM
    # start. Only QEMU is inspected; no custom module or guest hook is loaded.
    return vm_session.main([sys.executable,str(Path(__file__).resolve()),'--resident'],
                           components=('qemu',),revoke_session=False)


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as error:print(str(error),file=sys.stderr);sys.exit(1)
