"""Live audio controls through PipeWire's PulseAudio interface; no service/config changes."""
from __future__ import annotations

from collections import defaultdict
import json
import os
import subprocess

KINDS={'playback':('sink-input','sink'), 'recording':('source-output','source')}
NORMAL=65536


def pactl(*args):
    result=subprocess.run(['pactl',*map(str,args)],capture_output=True,text=True,timeout=5,
                          env={**os.environ,'LC_ALL':'C'})
    if result.returncode:
        raise RuntimeError((result.stderr or 'The audio server did not accept this change.').strip())
    return result.stdout.strip()


def listing(kind):
    result=json.loads(pactl('-f','json','list',kind+'s'))
    if not isinstance(result,list):raise ValueError('The audio server returned an invalid device list.')
    return result


def is_meter(stream):
    props=stream.get('properties',{})
    return (stream.get('resample_method')=='peaks' or props.get('stream.monitor') in ('true',True)
            or (props.get('application.id')=='org.PulseAudio.pavucontrol' and props.get('media.name')=='Peak detect'))


def app_key(stream):
    props=stream.get('properties',{})
    for key in ('application.id','application.process.binary','application.name'):
        if props.get(key):return key+':'+str(props[key]).casefold()
    client=stream.get('client')
    return 'client:'+str(client) if client not in (None,4294967295) else 'stream:'+str(stream['index'])


def identity(item):
    props=item.get('properties',{})
    return (item['index'],str(props.get('object.serial','')),item.get('client'),
            str(props.get('application.process.id','')),app_key(item))


def channel_values(item):
    volume=item.get('volume',{})
    names=item.get('channel_map','').split(',')
    ordered=[volume[name] for name in names if name in volume]
    if len(ordered)!=len(volume):ordered=list(volume.values())
    return [max(0,int(channel.get('value',0))) for channel in ordered]


def level(items):
    return round(max((v for item in items for v in channel_values(item)),default=0)*100/NORMAL)


def groups(streams,kind):
    grouped=defaultdict(list)
    for stream in streams:
        if not is_meter(stream):grouped[app_key(stream)].append(stream)
    result=[]
    for key,members in grouped.items():
        props=members[0].get('properties',{})
        name=props.get('application.name') or props.get('application.process.binary') or props.get('media.name') or 'Audio application'
        result.append({'key':key,'kind':kind,'name':str(name),'streams':members,
                       'icon':props.get('application.icon_name',''),
                       'app_id':props.get('application.id',''),'binary':props.get('application.process.binary',''),
                       'volume':level(members),'muted':all(s.get('mute',False) for s in members),
                       'part_muted':any(s.get('mute',False) for s in members) and not all(s.get('mute',False) for s in members),
                       'active':any(not s.get('corked',False) for s in members)})
    return sorted(result,key=lambda group:(group['name'].casefold(),group['key']))


def snapshot():
    info=json.loads(pactl('-f','json','info'))
    devices={kind:listing(kind) for kind in ('sink','source')}
    streams={kind:groups(listing(stream),kind) for kind,(stream,_) in KINDS.items()}
    return {'devices':devices,'apps':streams,
            'defaults':{kind:info.get('default_'+kind+'_name','') for kind in devices}}


def scaled_channels(item,percent,reference):
    target=round(float(percent)*NORMAL/100)
    values=channel_values(item)
    if not values:return []
    return [str(round(value*target/reference) if reference else target) for value in values]


def validate_level(value):
    value=float(value)
    if not 0<=value<=1000:raise ValueError('Choose a volume between 0% and 1000%.')
    return value


def apply_app(group,action,value):
    stream_kind,device_kind=KINDS[group['kind']]
    expected={identity(s) for s in group['streams']}
    current=[s for s in listing(stream_kind) if identity(s) in expected and not is_meter(s)]
    if not current:raise ValueError(group['name']+' is no longer using audio.')
    if action=='volume':value=validate_level(value)
    elif action=='device':
        if not any(d['name']==value for d in listing(device_kind)):
            raise ValueError('That audio device disconnected. Choose another device.')
    elif action!='mute':raise ValueError('Unknown mixer action.')
    reference=max((v for s in current for v in channel_values(s)),default=0)
    changed=0
    for stream in current:
        if action=='volume':
            if not stream.get('has_volume',True) or not stream.get('volume_writable',True):continue
            channels=scaled_channels(stream,value,reference)
            if not channels:continue
            command=['set-'+stream_kind+'-volume',str(stream['index']),*channels]
        elif action=='mute':command=['set-'+stream_kind+'-mute',str(stream['index']),'1' if value else '0']
        else:command=['move-'+stream_kind,str(stream['index']),value]
        try:pactl(*command);changed+=1
        except RuntimeError:
            # A closing app is normal. Never retry a reused stream ID against a different app.
            if any(identity(s)==identity(stream) for s in listing(stream_kind)):raise
    return changed


def apply_device(kind,device,action,value):
    if kind not in ('sink','source'):raise ValueError('Unknown device kind.')
    current=next((d for d in listing(kind) if d['name']==device['name']
                  and identity(d)==identity(device)),None)
    if current is None:raise ValueError('That audio device disconnected. Refresh devices.')
    if action=='volume':
        value=validate_level(value);values=channel_values(current)
        if values:pactl('set-'+kind+'-volume',current['name'],*scaled_channels(current,value,max(values)))
    elif action=='mute':pactl('set-'+kind+'-mute',current['name'],'1' if value else '0')
    elif action=='default':
        stream_kind='sink-input' if kind=='sink' else 'source-output'
        previous=[s for s in listing(stream_kind) if not is_meter(s)]
        pactl('set-default-'+kind,current['name'])
        for stream in previous:
            try:pactl('move-'+stream_kind,str(stream['index']),current['name'])
            except RuntimeError:
                if any(identity(s)==identity(stream) for s in listing(stream_kind)):raise
    else:raise ValueError('Unknown device action.')
