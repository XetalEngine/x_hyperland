#!/usr/bin/env python3
"""Read-only status modules; no connection or radio state is changed."""
import html
import json
from pathlib import Path
import subprocess
import sys


def read(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=4)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Status unavailable')
    return result.stdout.strip()


def status(kind):
    if kind == 'temperature':
        values=[]
        for sensor in Path('/sys/class/hwmon').glob('hwmon*'):
            try:
                name=(sensor/'name').read_text().strip()
                if name not in ('coretemp','k10temp','zenpower','cpu_thermal','acpitz'):continue
                values += [int(p.read_text())/1000 for p in sensor.glob('temp*_input')]
            except (OSError,ValueError):pass
        if not values:return {'text':' —','class':'unavailable','tooltip':'No temperature sensor is available'}
        value=max(values)
        return {'text':f' {value:.0f}°','class':'critical' if value>=90 else 'normal','tooltip':'CPU temperature · Click for system controls'}
    if kind in ('wifi','lan'):
        rows=read(['nmcli','-t','-f','DEVICE,TYPE,STATE','device','status']).splitlines()
        types=('wifi','802-11-wireless') if kind=='wifi' else ('ethernet','802-3-ethernet','bridge')
        devices=[row.split(':') for row in rows if len(row.split(':'))>=3 and row.split(':')[1] in types]
        devices.sort(key=lambda row:row[2]!='connected')
        radio=read(['nmcli','radio','wifi']) if kind=='wifi' else 'enabled'
        device=devices[0][0] if devices else ''
        details=read(['nmcli','-g','GENERAL.STATE,GENERAL.CONNECTION','device','show',device]).splitlines() if device else []
        state=details[0] if details else 'No adapter'
        connection=details[1] if len(details)>1 else ''
        connected=state.startswith('100 ')
        text=(('󰤨 '+connection[:16]) if connected else ('󰖪 Wi-Fi off' if radio=='disabled' else '󰤭 Wi-Fi —')) if kind=='wifi' else ('󰈀 LAN' if connected else '󰈂 LAN —')
        return {'text':text,'class':'connected' if connected else 'disconnected',
                'tooltip':html.escape(device+': '+state)+'\n'+html.escape(connection)+'\nClick for network controls'}
    if kind == 'internet':
        state = read(['nmcli', '-g', 'CONNECTIVITY', 'general'])
        return {'text': '󰅟' if state == 'full' else '󰅛', 'class': 'online' if state == 'full' else 'offline',
                'tooltip': 'Internet: ' + html.escape(state) + '\nClick for network controls'}
    if kind == 'vpn':
        devices = read(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE', 'device', 'status'])
        active = [row.split(':', 1)[0] for row in devices.splitlines()
                  if (':wireguard:' in row or ':tun:' in row) and ':connected' in row]
        connections = read(['nmcli', '-t', '-f', 'TYPE,NAME', 'connection', 'show', '--active'])
        active += [row.split(':', 1)[1] for row in connections.splitlines() if row.startswith('vpn:')]
        return {'text': '󰌾 VPN' if active else '󰌿', 'class': 'connected' if active else 'disconnected',
                'tooltip': ('Active VPN: ' + html.escape(', '.join(active)) if active else 'No active VPN') + '\nClick for connections / VPN'}
    raise ValueError('Unknown module')


try:
    print(json.dumps(status(sys.argv[1]), ensure_ascii=False))
except Exception as error:
    print(json.dumps({'text': '—', 'class': 'unavailable', 'tooltip': html.escape(str(error))}))
