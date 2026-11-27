#!/usr/bin/env python3
"""Author legacy synthesized miniatures. Build-only: Python + NumPy + FFmpeg.

No samples, recordings, pretrained audio or third-party melodies are used.
The compositions, synthesis and resulting audio are covered by the repo's MIT
license. Runtime only needs the committed MP3 files and PipeWire/PulseAudio.
This synthesizer does not reproduce the owner-supplied replacement collection.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1] / 'config/hypr'
sys.path.insert(0, str(ROOT))
from sounds.model import PACKS, EVENTS

RATE = 48000
# tonic, voice, unique opening melody (semitones), beat spacing
SCORES = {
    'integra': (62, 'pearlkeys', [0, 7, 9, 16, 14, 12], .37),
    'killerinstinct': (52, 'arcade94', [0,7,3,10,7,12,19], .29),
    'kitemple': (62, 'jadebell', [0,7,14,12,7,3], .40),
    'kiprimal': (47, 'stormwood', [0,3,10,7,0,12], .36),
    'kifireice': (57, 'thermal', [0,12,7,15,10,19,12], .31),
    'starcraft': (55, 'comms', [0, 7, 14, 10, 12, 19, 12], .34),
    'mortalkombat2': (50, 'outworld', [0, 7, 12, 3, 10, 7, 0], .30),
    'facadasexu': (55, 'copper', [0, 7, 3, 10, 7, 14, 12], .39),
    'prisonbreak': (60, 'breakout', [0, 3, 7, 12, 10, 15], .32),
    'mystery98': (57, 'clockwork', [0, 7, 3, 14, 10, 12], .41),
    'ghostbusters': (62, 'ectoplasm', [0, 7, 3, 10, 14, 12], .36),
    'hp4': (57, 'pitlane', [0, 7, 12, 19, 14, 12], .27),
    'amazon': (64, 'river', [0, 7, 9, 12, 16, 19], .40),
    'leviathan': (50, 'reliquary', [0, 7, 10, 3, 14, 12], .44),
    'polaris': (67, 'polar', [0, 7, 14, 12, 19, 16], .38),
    'infernalencore': (52, 'encore', [0, 0, 7, 10, 7, 3], .29),
    'midnightrun': (63, 'neon', [0, 7, 12, 10, 14, 7], .27),
    'platform95': (65, 'station95', [0, 4, 7, 12, 9, 4], .31),
    'mycelium': (64, 'spore', [0, 7, 10, 14, 12, 7], .42),
    'atomicafterglow': (57, 'isotope', [0, 7, 14, 11, 7, 12], .33),
    'blackwood': (55, 'harbour', [0, 7, 10, 14, 7, 2], .43),
    'midnighttransit': (60, 'transit', [7, 12, 4, 9, 7, 0], .36),
    'hyperfusionblue': (62, 'keys', [0, 7, 12, 9, 16, 19], .36),
    'raw': (62, 'crystal', [0, 7, 12, 16, 14, 19], .34),
    'modern': (64, 'keys', [0, 4, 11, 7, 14], .43),
    'breakpoint': (48, 'analog', [0, 7, 10, 12, 7], .40),
    'binaryknife': (66, 'glass', [0, 7, 3, 14, 12, 19], .32),
    'tidalglass': (59, 'water', [0, 7, 9, 14, 16], .44),
    'porcelainink': (57, 'string', [0, 7, 12, 9, 4], .46),
    'obsidianforge': (48, 'bronze', [0, 3, 7, 10, 12], .44),
    'candycloud': (65, 'musicbox', [0, 4, 7, 12, 16, 19], .33),
    'shadowedge': (62, 'flute', [0, 3, 7, 10, 7], .45),
    'hollowgrove': (67, 'wood', [0, 2, 7, 9, 12, 7], .38),
    'gildedhollow': (64, 'gold', [0, 7, 9, 12, 14, 19], .35),
}

# Original synthesized voices: ratio, FM depth, decay, overtone, gain, bass, attack.
KI_VOICES = {
    'arcade94': (2.0, 1.45, 4.0, 3.01, .16, .18, .018),
    'jadebell': (1.413, .35, 2.8, 2.76, .27, .06, .026),
    'stormwood': (1.0, .2, 5.2, 3.96, .22, .23, .024),
    'thermal': (2.003, .65, 3.4, 4.01, .24, .12, .030),
}


def voice(midi, duration, kind, seed=0):
    t = np.arange(round(duration * RATE)) / RATE
    f = 440 * 2 ** ((midi - 69) / 12)
    phase = 2 * np.pi * f * t
    attack = .012
    if kind in KI_VOICES:
        ratio,depth,decay,upper,gain,bass,attack = KI_VOICES[kind]
        out = np.sin(phase+depth*np.sin(phase*ratio)*np.exp(-9*t))*np.exp(-decay*t)
        out += gain*np.sin(phase*upper)*np.exp(-8*t)
        out += bass*np.sin(phase*.5)*np.exp(-3*t)*(1-np.exp(-18*t))
    elif kind == 'pearlkeys':
        out = np.sin(phase+.24*np.sin(phase*2.002)*np.exp(-7*t))*np.exp(-3.1*t)
        out += .12*np.sin(phase*3.002)*np.exp(-7*t)
        out += .12*np.sin(phase*.5)*np.exp(-2.6*t)*(1-np.exp(-14*t))
        attack = .035
    elif kind == 'pitlane':
        out = np.sin(phase + .42*np.sin(phase*2)*np.exp(-12*t))*np.exp(-5*t)
        out += .18*np.sin(phase*.5)*np.exp(-3*t)*(1-np.exp(-24*t))
        out += .06*np.sin(phase*4)*np.exp(-15*t)
        attack = .018
    elif kind == 'comms':
        # Clean FM comms chirp over a quiet reactor fundamental; original synthesis.
        out = np.sin(phase+.85*np.sin(phase*2.001)*np.exp(-8*t))*np.exp(-3.3*t)
        out += .13*np.sin(phase*.5)*np.exp(-2.7*t)*(1-np.exp(-15*t))
        out += .08*np.sin(phase*3.008)*np.exp(-9*t)
        out *= .92+.08*np.cos(2*np.pi*12*t)*np.exp(-4*t)
        attack = .028
    elif kind == 'outworld':
        # Original arcade gong and a short synth pulse, with no game samples.
        out = np.sin(phase+.8*np.sin(phase*1.41)*np.exp(-9*t))*np.exp(-3.4*t)
        out += .20*np.sin(phase*2.76)*np.exp(-7*t)
        out += .11*np.sin(phase*5.40)*np.exp(-12*t)
        out += .15*np.sin(phase*.5)*np.exp(-3*t)*(1-np.exp(-18*t))
        attack = .022
    elif kind == 'copper':
        # An original, quiet struck-metal and wood voice; no sampled rituals.
        out = np.sin(phase)*np.exp(-3.8*t)
        out += .19*np.sin(phase*2.013)*np.exp(-6.5*t)
        out += .08*np.sin(phase*3.96)*np.exp(-10*t)
        out += .16*np.sin(phase*.5)*np.exp(-3*t)*(1-np.exp(-18*t))
        attack = .024
    elif kind == 'breakout':
        # Original synth pulse with a brief metallic overtone and soft bass.
        out = np.sin(phase+.65*np.exp(-10*t)*np.sin(phase*2))*np.exp(-3.2*t)
        out += .14*np.sin(phase*.5)*np.exp(-2.7*t)*(1-np.exp(-14*t))
        out += .08*np.sin(phase*3.01)*np.exp(-9*t)
        attack = .032
    elif kind == 'clockwork':
        # Quiet struck tines above a warm string resonance; an original motif.
        out = np.sin(phase)*np.exp(-3.4*t)
        out += .17*np.sin(phase*2.002)*np.exp(-6*t)
        out += .07*np.sin(phase*3.98)*np.exp(-11*t)
        out += .15*np.sin(phase*.5+.015*np.sin(t*9))*np.exp(-2.5*t)*(1-np.exp(-12*t))
        attack = .035
    elif kind == 'keys':
        out = np.sin(phase + 1.3 * np.exp(-5*t) * np.sin(phase*2)) * np.exp(-2.6*t)
        out += .12 * np.sin(phase * .5) * np.exp(-2*t)
    elif kind == 'analog':
        out = sum(np.sin(phase*h) * np.exp(-(2.6+h)*t) / h**1.7 for h in range(1, 7))
        out += .16 * np.sin(phase*.5) * np.exp(-3*t); attack = .018
    elif kind == 'neon':
        out = np.sin(phase + .85*np.exp(-7*t)*np.sin(phase*2))*np.exp(-3.2*t)
        out += .16*np.sin(phase*2.004)*np.exp(-5.5*t)
        out += .12*np.sin(phase*.5)*np.exp(-2.4*t)*(1-np.exp(-18*t))
        attack = .032
    elif kind == 'encore':
        # Muted string harmonics with a quiet fifth; restrained drive, no samples.
        out = sum(np.sin(phase*h)*np.exp(-(3.8+h*.85)*t)/h**1.6 for h in range(1,9))
        out += .16*np.sin(phase*1.4983)*np.exp(-4.2*t)
        out = np.tanh(out*1.2)/1.2
        out += .08*np.sin(phase*.5)*np.exp(-3*t)
        attack = .024
    elif kind == 'ectoplasm':
        # An original liquid synth voice, never a sample of the film score.
        bend = .38*np.exp(-18*t) + .035*np.sin(2*np.pi*5*t)*(1-np.exp(-8*t))
        out = np.sin(phase+bend)*np.exp(-3*t)
        out += .16*np.sin(phase*2+.7*np.exp(-15*t))*np.exp(-6*t)
        out += .10*np.sin(phase*.5)*np.exp(-2.4*t)*(1-np.exp(-14*t))
        attack = .035
    elif kind == 'river':
        # Original bamboo-like fundamental with quiet droplet harmonics.
        out = np.sin(phase+.12*np.sin(phase*2)*np.exp(-12*t))*np.exp(-4.1*t)
        out += .13*np.sin(phase*2.76)*np.exp(-9*t)
        out += .06*np.sin(phase*4.03)*np.exp(-13*t)
        out += .10*np.sin(phase*.5)*np.exp(-2.6*t)*(1-np.exp(-14*t))
        attack = .038
    elif kind == 'reliquary':
        # Soft struck brass, a delayed low resonance and a gentle attack.
        out = np.sin(phase)*np.exp(-3*t)
        out += .18*np.sin(phase*2.003)*np.exp(-4.5*t)
        out += .07*np.sin(phase*3.97)*np.exp(-8*t)
        out += .12*np.sin(phase*.5)*np.exp(-2.4*t)*(1-np.exp(-9*t))
        attack = .045
    elif kind == 'polar':
        # Soft glass resonance with a delayed warm fundamental, no samples.
        out = np.sin(phase)*np.exp(-2.8*t)
        out += .15*np.sin(phase*2.002)*np.exp(-4.8*t)
        out += .06*np.sin(phase*4.004)*np.exp(-8*t)
        out += .13*np.sin(phase*.5)*np.exp(-2.3*t)*(1-np.exp(-12*t))
        attack = .045
    elif kind == 'string':
        out = sum(np.sin(phase*h + .025*np.sin(t*13)) * np.exp(-(2.5+h*.7)*t) / h**1.5 for h in range(1, 10))
        out += .16 * np.sin(phase*2.008) * np.exp(-6*t)
    elif kind == 'spore':
        out = np.sin(phase+.012*np.sin(t*9))*np.exp(-3.1*t)
        out += .18*np.sin(phase*2.006)*np.exp(-5*t)+.11*np.sin(phase*2.71)*np.exp(-12*t)
        out += .12*np.sin(phase*.5)*np.exp(-2.3*t)*(1-np.exp(-14*t))
        attack = .045
    elif kind == 'isotope':
        out = np.sin(phase + .6*np.sin(phase*2)*np.exp(-6*t))*np.exp(-3*t)
        out += .12*np.sin(phase*.5)*np.exp(-2*t) + .06*np.sin(phase*3.002)*np.exp(-9*t)
        attack = .035
    elif kind == 'harbour':
        out = np.sin(phase)*np.exp(-3.2*t) + .20*np.sin(phase*2.72)*np.exp(-9*t)
        out += .13*np.sin(phase*.5)*np.exp(-2.4*t) + .07*np.sin(phase*4.03)*np.exp(-12*t)
        attack = .025
    elif kind == 'wood':
        out = np.sin(phase)*np.exp(-4*t) + .30*np.sin(phase*2.76)*np.exp(-14*t)
        out += .09*np.sin(phase*5.4)*np.exp(-24*t)
        out += .18*np.sin(phase*.5 + .008*np.sin(2*np.pi*4*t))*np.exp(-2.8*t)*(1-np.exp(-t*18))
    elif kind == 'flute':
        vibrato = .018*np.sin(2*np.pi*4.3*t)*(1-np.exp(-4*t))
        out = (np.sin(phase+vibrato) + .16*np.sin(phase*2) + .05*np.sin(phase*3))*np.exp(-2.1*t)
        noise = np.random.default_rng(seed).normal(0, .024, len(t))
        out += np.convolve(noise, np.ones(9)/9, 'same') * np.exp(-4*t); attack = .065
    else:
        # Different modal resonances and decay rates give every material its own voice.
        modes = {
            'station95': [(1, 1, 3.7), (2.001, .19, 6.2), (3.98, .08, 10.5), (.5, .09, 3.2)],
            'transit': [(1, 1, 3.1), (2.002, .22, 5.4), (3, .10, 8), (4.01, .04, 10)],
            'crystal': [(1, 1, 3.2), (2, .24, 5), (4, .08, 9)],
            'glass': [(1, 1, 3.8), (2.003, .32, 6), (3.997, .11, 11)],
            'water': [(1, 1, 2.7), (2.01, .14, 5), (3, .06, 8)],
            'bronze': [(1, 1, 3), (2.006, .38, 4.8), (2.76, .13, 12), (4.07, .09, 15)],
            'musicbox': [(1, 1, 3.1), (2, .28, 4.2), (4.003, .16, 7), (6, .04, 13)],
            'gold': [(1, 1, 2.8), (2.002, .32, 4.5), (3, .15, 7), (4.01, .09, 10)],
        }[kind]
        bend = .035*np.exp(-24*t) if kind == 'water' else 0
        out = sum(a*np.sin(phase*r + bend) * np.exp(-d*t) for r,a,d in modes)
        if kind == 'gold': out += .18*np.sin(phase*.5)*np.exp(-2*t)*(1-np.exp(-30*t))
    # Raised-cosine edges avoid clicks, even on short alert notes.
    out *= np.sin(np.minimum(t/attack, 1)*np.pi/2)**2
    release = min(.22, duration*.3)
    out *= np.sin(np.minimum((duration-t)/release, 1)*np.pi/2)**2
    return out


def score(pack, event):
    tonic, kind, motif, beat = SCORES[pack]
    minor = pack in ('killerinstinct','kitemple','kiprimal','kifireice','starcraft', 'mortalkombat2', 'facadasexu', 'leviathan', 'infernalencore', 'midnightrun', 'mycelium', 'blackwood', 'breakpoint', 'binaryknife', 'obsidianforge', 'shadowedge')
    third = 3 if minor else 4
    # time, midi note, length, gain, stereo pan
    if event == 'startup':
        notes = [(i*beat+.07, tonic+n, 1.4, .65 if i else .80, (i%3-1)*.25) for i,n in enumerate(motif)]
        end = (len(motif)-1)*beat+.07
        notes += [(end, tonic-12+n, 1.55, .17, pan) for n,pan in [(0,-.2),(7,.2)]]
        length = 4.15
    elif event == 'shutdown':
        ending = [motif[3], 7, third, 0]
        notes = [(.07+i*.39, tonic+n, 1.35, .62-i*.055, (i-1.5)*.14) for i,n in enumerate(ending)]
        notes += [(1.24,tonic-12,1.35,.21,0)];length = 3.05
    else:
        patterns = {
            'error': ([0,-3,-7], [.04,.19,.38], .55, .95),
            'warning': ([7,7], [.04,.24], .52, .85),
            'info': ([7,12], [.04,.20], .60, .90),
            'question': ([0,2,7], [.04,.20,.38], .57, 1.12),
            'success': ([0,third,7,12], [.04,.16,.28,.43], .60, 1.18),
            'notification': ([0,7], [.04,.17], .48, .82),
        }
        pitches,times,note_length,length = patterns[event]
        notes = [(at,tonic+n,note_length,.62,(i-(len(pitches)-1)/2)*.15) for i,(n,at) in enumerate(zip(pitches,times))]
    audio = np.zeros((round(length*RATE),2))
    for i,(at,note,duration,gain,pan) in enumerate(notes):
        start=round(at*RATE); tone=voice(note,duration,kind,seed=i+sum(map(ord,pack)))
        tone=tone[:len(audio)-start]*gain
        audio[start:start+len(tone),0] += tone * np.sqrt((1-pan)/2)
        audio[start:start+len(tone),1] += tone * np.sqrt((1+pan)/2)
    dry=audio.copy()
    for delay,level in [(.043,.12),(.079,.09),(.137,.065),(.211,.042),(.317,.026)]:
        n=round(delay*RATE);audio[n:] += dry[:-n,::-1]*level
    # Gentle saturation plus consistent RMS and generous peak headroom.
    audio=np.tanh(audio*.85)
    active=audio[np.max(np.abs(audio),axis=1)>.003]
    rms=np.sqrt(np.mean(active**2)) if len(active) else 1
    gain=min(.105/rms,.55/np.max(np.abs(audio)))
    audio*=gain
    fade=round(.08*RATE);audio[-fade:]*=np.linspace(1,0,fade)[:,None]**2
    return audio


def main(selected=None, output=None, replace=False):
    if selected and set(selected)-PACKS.keys():raise ValueError('Unknown sound pack.')
    output=Path(output or ROOT/'sounds/packs')
    if not replace and any((output/pack/(event+'.mp3')).exists() for pack in selected or PACKS for event in EVENTS):
        raise FileExistsError('Sound packs already exist. Use --output for authoring; --replace explicitly replaces them with the legacy score.')
    manifest={'version':2,'format':'mp3','sample_rate':RATE,'license':'MIT','packs':{}}
    if (output/'catalog.json').is_file():manifest=json.loads((output/'catalog.json').read_text())
    for pack,(_,title,description,_) in PACKS.items():
        if selected and pack not in selected:continue
        target=output/pack;target.mkdir(parents=True,exist_ok=True)
        info={'title':title,'description':description,'events':{}}
        for event in EVENTS:
            audio=score(pack,event);destination=target/(event+'.mp3')
            with tempfile.TemporaryDirectory(prefix='fusion-audio-') as tmp:
                wav=Path(tmp)/'source.wav'
                with wave.open(str(wav),'wb') as stream:
                    stream.setnchannels(2);stream.setsampwidth(2);stream.setframerate(RATE)
                    stream.writeframes((audio*32767).round().astype('<i2').tobytes())
                subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(wav),'-map_metadata','-1',
                    '-c:a','libmp3lame','-q:a','4','-metadata','artist=Xetal Fusion',
                    '-metadata','title='+title+' · '+event,'-metadata','copyright=MIT · XetalEngine',str(destination)],check=True)
            decoded=subprocess.check_output(['ffmpeg','-v','error','-nostdin','-i',str(destination),'-f','f32le','-'])
            samples=np.frombuffer(decoded,dtype='<f4').reshape(-1,2)
            envelope=[round(float(np.max(np.abs(chunk))),4) for chunk in np.array_split(samples,96)]
            info['events'][event]={'seconds':len(samples)/RATE,'sample_rate':RATE,'channels':2,'peak_dbfs':round(float(20*np.log10(np.max(np.abs(samples)))),2),'waveform':envelope,
                'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}
        manifest['packs'][pack]=info
        print(pack+': 8 original sounds',flush=True)
    (output/'catalog.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packs',nargs='*');parser.add_argument('--output',type=Path)
    parser.add_argument('--replace',action='store_true')
    args=parser.parse_args();main(args.packs or None,args.output,args.replace)
