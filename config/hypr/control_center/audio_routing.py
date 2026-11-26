"""Distinguish following the system default from a deliberately pinned device."""
from __future__ import annotations

import json
import os
import subprocess

SYSTEM_DEFAULT='@SYSTEM_DEFAULT@'


def targets():
    """Read only routing metadata, not the full PipeWire graph or saved volumes."""
    try:
        result=subprocess.run(['pw-dump','-N','default'],capture_output=True,text=True,timeout=2,
                              env={**os.environ,'LC_ALL':'C'})
        if result.returncode:return None
        objects=json.loads(result.stdout)
        metadata=next(item for item in objects if item.get('type')=='PipeWire:Interface:Metadata'
                      and item.get('props',{}).get('metadata.name')=='default')
        values={}
        for item in metadata.get('metadata',[]):
            if item.get('key') in ('target.object','target.node'):
                values.setdefault(str(item['subject']),{})[item['key']]=str(item['value'])
        return values
    except (OSError,subprocess.SubprocessError,ValueError,TypeError,KeyError,StopIteration):return None


def selection(stream,kind,devices,default,metadata):
    props=stream.get('properties',{})
    actual=next((d['name'] for d in devices if 'index' in d and d['index']==stream.get(kind)),None)
    if metadata is None:return actual  # Do not call an unknown/pinned route System Default.
    route=metadata.get(str(props.get('object.id','')), {})
    for key,device_key in (('target.object','object.serial'),('target.node','object.id')):
        if key in route:
            value=str(route[key])
            if value=='-1':return SYSTEM_DEFAULT
            return next((d['name'] for d in devices if value in
                         (d['name'],str(d.get('properties',{}).get(device_key,'')))), 'unavailable:'+value)
    # Client-selected defaults are followed by WirePlumber too. Explicit client
    # targets elsewhere remain visible, including choices made outside Fusion.
    value=props.get('target.object',props.get('node.target'))
    if value not in (None,'',-1,'-1'):
        key='object.serial' if 'target.object' in props else 'object.id'
        target=next((d['name'] for d in devices if str(value) in
                     (d['name'],str(d.get('properties',{}).get(key,'')))),None)
        return SYSTEM_DEFAULT if target==default else target or 'unavailable:'+str(value)
    return SYSTEM_DEFAULT if actual in (None,default) else actual


def pin(stream,device):
    """Pin even a device that happens to be the current system default.

    PulseAudio's move-to-default clears the preference, so use WirePlumber's
    target metadata for explicit choices. Return False for a non-PipeWire stream.
    """
    node=stream.get('properties',{}).get('object.id')
    serial=device.get('properties',{}).get('object.serial')
    if node is None or serial is None:return False
    try:node,serial=int(node),int(serial)
    except (ValueError,TypeError):raise ValueError('The audio device identity changed. Refresh devices.')
    if node<=0 or serial<=0:raise ValueError('The audio device identity changed. Refresh devices.')
    result=subprocess.run(['pw-metadata','-n','default',str(node),'target.object',str(serial),'Spa:Id'],
                          capture_output=True,text=True,timeout=2,env={**os.environ,'LC_ALL':'C'})
    if result.returncode:raise RuntimeError((result.stderr or 'Could not set the app output.').strip())
    return True
