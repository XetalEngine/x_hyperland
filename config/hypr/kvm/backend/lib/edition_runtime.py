"""Optional integrated desktop preflight; standalone vmstart_2 stays portable."""
from pathlib import Path
import json
import os
import shlex
import subprocess
import sys

_inspections={}


def managed_module(cfg):
    runtime=Path(__file__).resolve().parents[2]/'module_policy.py'
    if not runtime.is_file():return False
    import module_policy
    return module_policy.managed(cfg.data)


def inspection(binary,query):
    """Read build capabilities through the same authenticated memory owner.

    Plain/standalone QEMU keeps the original direct probe. In the GUI, cache
    only public device information; the actual launch always reauthorizes.
    """
    runtime=Path(__file__).resolve().parents[2]/'runtime_probe.py'
    executable=Path(binary).resolve()
    descriptor=executable.parent.parent/'.vm-runtime.json'
    if not runtime.is_file() or not descriptor.is_file():return None
    if os.geteuid()==0 and os.environ.get('XETAL_KVM_LAUNCH_SOCKET'):return None
    import portable
    if executable!=(portable.component_path('qemu')/'bin/qemu-system-x86_64').resolve():
        raise OSError('Select this build in KVM Settings before checking its devices.')
    identity=(str(executable),executable.stat().st_mtime_ns,descriptor.read_bytes())
    if identity not in _inspections:
        reply=subprocess.run(['sudo','-n','/usr/bin/env',
            'XETAL_KVM_DATA='+str(portable.data_root()),'XETAL_KVM_EDITION=xetallic',
            sys.executable,str(runtime)],capture_output=True,text=True,timeout=60)
        if reply.returncode:
            raise OSError('Sign in to Echo and use Launch VM to complete the QEMU checks. '+reply.stderr.strip()[-800:])
        try:
            result=json.loads(reply.stdout)
            if not isinstance(result,dict) or not isinstance(result['capabilities']['devices'],list):raise ValueError()
        except (ValueError,KeyError,TypeError):raise OSError('The QEMU device check returned an invalid result.') from None
        _inspections.clear();_inspections[identity]=result
    result=_inspections[identity]
    if query in result.get('errors',{}):raise OSError(result['errors'][query])
    value=result[query]
    if query=='capabilities':value=dict(value,devices=set(value['devices']))
    return value


def command(argv, cfg=None):
    runtime=Path(__file__).resolve().parents[2]/'vm_session.py'
    if not runtime.is_file():return argv
    options=[]
    # Windowed launch modes skip Single GPU's shell hooks. Honor the same
    # optional published module there, before any device/network preparation.
    settings=cfg.data.get('tools',{}) if cfg is not None else {}
    if (cfg is not None and cfg.data.get('_meta',{}).get('vm_edition')=='xetallic'
            and settings.get('kvm_build_enabled')
            and Path(settings.get('kvm_build','')).resolve()==runtime.with_name('module-tool.sh')):
        if shlex.split(settings.get('kvm_build_args','')):
            raise ValueError('Use the default module load action for Virtual GPU and Dual GPU.')
        options=['--module-options',json.dumps(settings.get('kvm_env') or {})]
    return [sys.executable,str(runtime),*options,'--',*argv]
