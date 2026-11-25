#!/usr/bin/env python3
"""Decode shipped MP3 cues and verify duration, levels, previews and hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]/'config/hypr'
sys.path.insert(0,str(ROOT))
from sounds.model import EVENTS,PACKS,asset

def main(selected=None):
    catalog=json.loads((ROOT/'sounds/packs/catalog.json').read_text())
    seen=set();peaks=[]
    assert set(catalog['packs'])==set(PACKS)
    for pack in selected or PACKS:
        assert set(catalog['packs'][pack]['events'])==set(EVENTS)
        for event in EVENTS:
            path=asset(pack,event);info=catalog['packs'][pack]['events'][event]
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest==info['sha256'] and digest not in seen,(pack,event,'hash')
            seen.add(digest)
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(path)]))
            stream=probe['streams'][0];rate=int(stream['sample_rate'])
            assert path.suffix=='.mp3' and stream['codec_name']=='mp3' and stream['channels']==2
            assert rate==info.get('sample_rate',catalog['sample_rate'])
            pcm=subprocess.check_output(['ffmpeg','-v','error','-nostdin','-i',str(path),'-f','f32le','-'])
            samples=np.frombuffer(pcm,dtype='<f4').reshape(-1,2)
            # Decode honours MP3 encoder delay/padding; container duration includes it.
            duration=len(samples)/rate
            assert 0<duration<4.8 and abs(duration-info['seconds'])<1/rate,(pack,event,duration)
            assert np.all(np.isfinite(samples))
            peak=float(np.max(np.abs(samples)));peaks.append(peak)
            assert .12<peak<.75,(pack,event,peak)
            # Fast percussive attacks are intentional; check the actual boundaries.
            assert np.max(np.abs(samples[0]))<.03 and np.max(np.abs(samples[-1]))<.01,(pack,event,'edge click')
            envelope=[round(float(np.max(np.abs(chunk))),4) for chunk in np.array_split(samples,96)]
            assert np.allclose(info['waveform'],envelope,atol=.0001),(pack,event,'waveform')
            assert abs(info['peak_dbfs']-20*np.log10(peak))<.02,(pack,event,'peak metadata')
    print(f'{len(seen)} MP3 system cues verified; worst decoded peak {20*np.log10(max(peaks)):.1f} dBFS.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packs',nargs='*')
    args=parser.parse_args()
    if set(args.packs)-PACKS.keys():parser.error('Unknown sound pack.')
    main(args.packs or None)
