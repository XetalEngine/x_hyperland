"""Complete TPM choices, prepared privately before the VM configuration changes."""
from pathlib import Path
import copy
import fcntl
import json
import os
import re
import secrets
import shlex
import struct
import subprocess
import sys
import uuid

import portable
import tpm_setup

PROPERTIES = {
    'TPM2_PT_LEVEL':0x101, 'TPM2_PT_REVISION':0x102,
    'TPM2_PT_DAY_OF_YEAR':0x103, 'TPM2_PT_YEAR':0x104,
    'TPM_PT_MANUFACTURER':0x105, 'TPM_PT_VENDOR_STRING_1':0x106,
    'TPM_PT_VENDOR_STRING_2':0x107, 'TPM_PT_VENDOR_STRING_3':0x108,
    'TPM_PT_VENDOR_STRING_4':0x109, 'TPM_PT_VENDOR_TPM_TYPE':0x10a,
    'TPM_PT_FIRMWARE_VERSION_1':0x10b, 'TPM_PT_FIRMWARE_VERSION_2':0x10c,
    'TPM2_PT_PS_FAMILY_INDICATOR':0x123, 'TPM2_PT_PS_LEVEL':0x124,
    'TPM2_PT_PS_REVISION':0x125, 'TPM2_PT_PS_DAY_OF_YEAR':0x126,
    'TPM2_PT_PS_YEAR':0x127,
}


def builder_reason(root):
    root=Path(root)
    required=('libtpms/build.sh','swtpm/build.sh','scripts/gen-tpm-vendor-identity-h.sh',
              'scripts/relink-origin.py')
    if not all((root/name).is_file() for name in required):
        return 'A local custom TPM builder is required. The published TPM remains available below.'
    return ''


def validate(values):
    from tabs_tpm import FIELDS
    result={}
    for key,label,kind,_ in FIELDS:
        value=str(values.get(key,'')).strip()
        if kind=='str':
            if not re.fullmatch(r'[A-Za-z0-9 ._()/+-]{1,60}',value):
                raise ValueError('Use a simple model name for '+label)
        else:
            try: number=int(value,0)
            except ValueError: raise ValueError('Enter a numeric value for '+label) from None
            if not 0<=number<=0xffffffff: raise ValueError('Invalid '+label)
            value=str(number) if kind=='dec' else ('0x%08X'%number if kind=='ascii4' else '0x%X'%number)
        result[key]=value
    if int(result['TPM_PT_MANUFACTURER'],0)==0:raise ValueError('A TPM manufacturer is required')
    return result


def environment_text(values):
    return '# KVM Settings TPM identity\n'+''.join(k+'='+shlex.quote(v)+'\n' for k,v in validate(values).items())


def read_host():
    """Only TPM2_GetCapability: no keys, clear, NV writes, or provisioning."""
    device=next((p for p in (Path('/dev/tpmrm0'),Path('/dev/tpm0')) if p.exists()),None)
    if device is None:raise RuntimeError('No host TPM was found. Enable TPM in firmware first.')
    with device.open('r+b',buffering=0) as stream:
        stream.write(struct.pack('>HIIIII',0x8001,22,0x17a,6,0x100,64))
        reply=stream.read(8192)
    if len(reply)<19:raise RuntimeError('The host TPM returned an incomplete reply')
    _,size,status=struct.unpack('>HII',reply[:10])
    if status or size!=len(reply) or struct.unpack('>I',reply[11:15])[0]!=6:
        raise RuntimeError('The host TPM could not return its public identity')
    count=struct.unpack('>I',reply[15:19])[0]
    if count>64 or len(reply)!=19+8*count:raise RuntimeError('Invalid host TPM property list')
    return dict(struct.unpack('>II',reply[19+8*i:27+8*i]) for i in range(count))


def host_identity():
    from tabs_tpm import PRESETS
    try: properties=read_host()
    except PermissionError:
        from uiutil import sudo_command
        command,env,available=sudo_command([sys.executable,str(Path(__file__).resolve()),'--read-host'],
                                           'KVM Settings: read the host TPM public identity')
        if not available:raise RuntimeError('Administrator access is needed to read the host TPM')
        result=subprocess.run(command,env=env,text=True,capture_output=True,timeout=45)
        if result.returncode:raise RuntimeError(result.stderr.strip() or 'Host TPM read cancelled')
        properties={int(k):int(v) for k,v in json.loads(result.stdout).items()}
    if 0x105 not in properties:raise RuntimeError('The host TPM did not report a manufacturer')
    values=copy.deepcopy(next((v for v in PRESETS.values() if int(v['TPM_PT_MANUFACTURER'],0)==properties[0x105]),next(iter(PRESETS.values()))))
    for key,number in PROPERTIES.items():
        if number in properties:values[key]=hex(properties[number])
    vendor=properties[0x105].to_bytes(4,'big').decode('ascii',errors='ignore').strip('\0 ')
    if not any(int(v['TPM_PT_MANUFACTURER'],0)==properties[0x105] for v in PRESETS.values()):
        values['TPM_IDENT_MODEL_JSON_TPM2']=vendor+' TPM 2.0'
        values['TPM_IDENT_MODEL_JSON_TPM12']=vendor
    return validate(values)


def choose(action, current):
    from tabs_tpm import PRESETS
    if action=='host':return host_identity(),'Host TPM identity'
    if action=='random':
        values=copy.deepcopy(secrets.choice(list(PRESETS.values())))
        values['TPM_IDENT_MODEL_JSON_TPM2']+=' '+secrets.token_hex(2).upper()
        values['TPM_PT_FIRMWARE_VERSION_2']=hex(secrets.randbelow(65536))
        return validate(values),'Random identity'
    if action.startswith('preset:'):
        name=action.split(':',1)[1]
        return validate(PRESETS[name]),name
    if action=='custom':return validate(current),'Custom identity'
    raise ValueError('Unknown TPM identity option')


def build(root, values, destination, report):
    root=Path(root)
    reason=builder_reason(root)
    if reason:raise RuntimeError(reason)
    destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    prefix=destination/'runtime'
    saved={p:p.read_bytes() if p.exists() else None for p in
           (root/'tpm_real_dump.env',root/'libtpms/src/tpm_vendor_identity.h')}
    with (root/'.identity.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        env=dict(os.environ,PREFIX=str(prefix),JOBS=str(min(8,os.cpu_count() or 2)))
        try:
            (root/'tpm_real_dump.env').write_text(environment_text(values))
            commands=[['bash',str(root/'scripts/gen-tpm-vendor-identity-h.sh'),
                       str(root/'tpm_real_dump.env'),str(root/'libtpms/src/tpm_vendor_identity.h')],
                      ['bash',str(root/'libtpms/build.sh')],['bash',str(root/'swtpm/build.sh')],
                      [sys.executable,str(root/'scripts/relink-origin.py'),'--prefix',str(prefix)]]
            with (destination/'build.log').open('w') as log:
                for message,command in zip(('Preparing identity…','Building private TPM library…',
                                            'Building private TPM tools…','Checking runtime paths…'),commands):
                    report(message)
                    result=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
                    if result.returncode:raise RuntimeError('TPM build failed. Your active TPM is unchanged.\nLog: '+str(destination/'build.log'))
        finally:
            for path,content in saved.items():
                if content is None:path.unlink(missing_ok=True)
                else:path.write_bytes(content)
    binary=prefix/'bin/swtpm'
    if not binary.is_file():raise RuntimeError('The build did not produce swtpm')
    return str(binary)


def verify(binary, state, values):
    data=(Path(state)/'tpm2-00.permall').read_bytes()
    stamp=Path(binary).stat().st_mtime_ns
    banks,cert=tpm_setup.inspect_state(binary,data,stamp)
    if 'sha256' not in banks or not cert:raise RuntimeError('The prepared TPM is missing its SHA-256 bank or certificate')
    actual=tpm_setup.inspect_state(binary,data,stamp,True)
    if values:
        mismatches=[key for key,number in PROPERTIES.items() if int(values[key],0)!=actual.get(number)]
        if mismatches:raise RuntimeError('The built TPM did not apply these properties: '+', '.join(mismatches))
    return actual


def prepare(action, tools, values, ensure_package, report):
    if action=='physical':
        device=Path('/dev/tpm0')
        if not device.is_char_device():raise RuntimeError('No compatible physical TPM device was found')
        return dict(mode='passthrough',device=str(device),label='Physical host TPM')
    report('Preparing TPM tools…');ensure_package()
    if action=='bundled':
        binary=str(portable.component_path('tpm')/'bin/swtpm');identity=None;label='Published TPM'
    else:
        reason=builder_reason(tools.get('tpm_root',''))
        if reason:raise RuntimeError(reason)
        report('Reading the host identity…' if action=='host' else 'Preparing the selected identity…')
        identity,label=choose(action,values)
    destination=portable.data_root()/'tpm-identities'/uuid.uuid4().hex
    destination.mkdir(parents=True,mode=0o700)
    if action!='bundled':binary=build(tools['tpm_root'],identity,destination,report)
    state=destination/'state'
    report('Creating private guest keys and certificates…')
    tpm_setup.initialize(state,binary,setup_binary=str(portable.component_path('tpm')/'bin/swtpm_setup'))
    report('Verifying the TPM that the guest will use…')
    actual=verify(binary,state,identity)
    if identity is None:
        from tabs_tpm import PRESETS
        identity=copy.deepcopy(next(iter(PRESETS.values())))
        for key,number in PROPERTIES.items():
            if number in actual:identity[key]=hex(actual[number])
        result=subprocess.run([binary,'socket','--tpm2','--print-info','2'],text=True,capture_output=True,check=True,timeout=15)
        identity['TPM_IDENT_MODEL_JSON_TPM2']=json.loads(result.stdout)['TPMAttributes']['model']
        identity=validate(identity)
    from packages import atomic_json
    atomic_json(destination/'identity.json',dict(values=identity,binary=binary,state=str(state),label=label))
    return dict(mode='emulator',binary=binary,state=str(state),values=identity,label=label)


def snapshot(tab):
    return dict(mode=tab.cfg.data.get('tpm_backend','emulator'),device=tab.pt_path.text(),cancel=tab.pt_cancel.text(),
                binary=tab.cfg.data.get('tools',{}).get('swtpm_binary',''),state=tab.state_dir.text(),
                values=copy.deepcopy(tab.cfg.data.get('tpm_identity') or getattr(tab,'loaded_identity',None)
                                     or {k:w['edit'].text() for k,w in tab.widgets.items()}),
                label=tab.cfg.data.get('tpm_choice','Previous TPM'))


def activate(tab, choice):
    cfg=tab.cfg;tools=cfg.data.setdefault('tools',{})
    for key,field in (('binary','swtpm_binary'),('state','swtpm_state')):
        if key in choice:tools[field]=choice[key]
    if 'state' in choice:tab.state_dir.setText(choice['state'])
    if 'values' in choice:
        cfg.data['tpm_identity']=copy.deepcopy(choice['values'])
        for key,value in choice['values'].items():
            tab.widgets[key]['edit'].setText(value);tab._decode(key)
    cfg.data['tpm_choice']=choice['label']
    current=cfg.simple.get('tpmdev','')
    match=re.search(r'\bid=([^,]+)',current);tid=match.group(1) if match else 'tpm-tpm0'
    if not any(str(d.get('driver','')).startswith('tpm-') and not d.get('_disabled') for d in cfg.devices):
        cfg.devices.append(dict(driver='tpm-crb',id='tpm0',tpmdev=tid))
    match=re.search(r'chardev=([^,]+)',current)
    chardev=match.group(1) if match else cfg.data.get('tpm_chardev','chrtpm')
    if not any(c.get('id')==chardev for c in cfg.data.get('chardevs',[])):
        cfg.data.setdefault('chardevs',[]).append({'_positional':['socket'],'id':chardev,
                                                 'path':str(portable.data_root()/'run/swtpm.sock')})
    tab._loading_backend=True
    tab.pt_path.setText(choice.get('device','/dev/tpm0'));tab.pt_cancel.setText(choice.get('cancel','/dev/null'))
    (tab.rb_passthrough if choice['mode']=='passthrough' else tab.rb_emulated).setChecked(True)
    tab._loading_backend=False
    tab._apply_backend(emit=False)


if __name__=='__main__':
    if sys.argv[1:]!=['--read-host']:raise SystemExit('Only --read-host is supported')
    try:print(json.dumps(read_host()))
    except Exception as error:print(str(error),file=sys.stderr);raise SystemExit(1)
