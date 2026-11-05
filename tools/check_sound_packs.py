#!/usr/bin/env python3
"""Decode every shipped sound and verify length, finite samples and headroom."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]/'config/hypr'
sys.path.insert(0,str(ROOT))
from sounds.model import EVENTS,PACKS

catalog=json.loads((ROOT/'sounds/packs/catalog.json').read_text())
seen=set();peaks=[]
for pack in PACKS:
    for event in EVENTS:
        path=ROOT/'sounds/packs'/pack/(event+'.ogg');info=catalog['packs'][pack]['events'][event]
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest==info['sha256'] and digest not in seen,(pack,event,'hash')
        seen.add(digest)
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
        stream=probe['streams'][0]
        assert stream['codec_name']=='vorbis' and stream['channels']==2 and int(stream['sample_rate'])==48000
        duration=float(probe['format']['duration'])
        assert 0<duration<5 and abs(duration-info['seconds'])<.01,(pack,event,duration)
        pcm=subprocess.check_output(['ffmpeg','-v','error','-nostdin','-i',str(path),'-f','f32le','-'])
        samples=np.frombuffer(pcm,dtype='<f4')
        assert np.all(np.isfinite(samples))
        peak=float(np.max(np.abs(samples)));peaks.append(peak)
        assert .12<peak<.75,(pack,event,peak)
        assert np.max(np.abs(samples[:200]))<.01 and np.max(np.abs(samples[-200:]))<.01,(pack,event,'edge click')
        assert len(info['waveform'])==96
assert set(catalog['packs'])==set(PACKS)
print(f'{len(seen)} unique stereo sounds verified; startup 4.15 s, shutdown 3.05 s; worst decoded peak {20*np.log10(max(peaks)):.1f} dBFS.')
