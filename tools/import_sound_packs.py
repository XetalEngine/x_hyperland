#!/usr/bin/env python3
"""Convert an owner-supplied HyperFusion WAV collection and install its cues.

Authoring dependencies: NumPy and FFmpeg. The source WAVs are never changed.
The output folder must be new; all conversions finish before it is published.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1] / 'config/hypr'
sys.path.insert(0, str(ROOT))
from sounds.model import EVENTS, PACKS

EVENT_NAMES = {'information': 'info', 'exclamation': 'warning'}
QUALITY = 4


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(name):
    return re.sub(r'[^a-z0-9]', '', name.lower())


def entries(source):
    names = {normalize(value[0]): key for key, value in PACKS.items()}
    manifest = json.loads((source / 'manifest.json').read_text())
    result = []; seen = set(); directories = {}
    for item in manifest:
        pack = names[normalize(item['theme'])]
        event = EVENT_NAMES.get(item['event'], item['event'])
        if event not in EVENTS or (pack, event) in seen:
            raise ValueError('Unknown or duplicate sound event: ' + str(item))
        path = source / item['file']
        if not path.resolve().is_relative_to(source) or path.suffix.lower() != '.wav':
            raise ValueError('Audio source must be a WAV inside the collection.')
        if pack in directories and directories[pack] != path.parent:
            raise ValueError('A theme spans multiple source folders: ' + pack)
        directories[pack] = path.parent
        result.append(dict(item, pack=pack, key=event, path=path))
        seen.add((pack, event))
    expected = {(pack, event) for pack in PACKS for event in EVENTS}
    if seen != expected:
        raise ValueError('The collection must contain all eight events for every theme.')
    for pack, directory in directories.items():
        path = directory / 'preview.wav'
        if path.is_file():
            result.append(dict(theme=PACKS[pack][0], event='preview', key='preview',
                               pack=pack, path=path, file=str(path.relative_to(source))))
    if {item['path'].resolve() for item in result} != set(source.rglob('*.wav')):
        raise ValueError('The collection has unlisted WAV files.')
    return sorted(result, key=lambda item: item['file'])


def convert(item, staging):
    source = item['path']; destination = staging / Path(item['file']).with_suffix('.mp3')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(source)) as stream:
        rate = stream.getframerate(); channels = stream.getnchannels()
        frames = stream.getnframes()
        if channels != 2 or stream.getsampwidth() != 2 or rate != 44100:
            raise ValueError('Expected the supplied 44.1 kHz, 16-bit stereo WAV: ' + str(source))
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(source),
                    '-map_metadata', '-1', '-map', '0:a:0', '-c:a', 'libmp3lame',
                    '-q:a', str(QUALITY), '-threads', '1',
                    '-metadata', 'artist=Hyper Fusion',
                    '-metadata', 'title=' + item['theme'] + ' · ' + item['event'],
                    str(destination)], check=True, timeout=60)
    decoded = subprocess.check_output(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(destination),
                                       '-map', '0:a:0', '-f', 'f32le', '-'], timeout=30)
    samples = np.frombuffer(decoded, dtype='<f4').reshape(-1, channels)
    if len(samples) != frames or not np.all(np.isfinite(samples)):
        raise ValueError('Decoded MP3 does not preserve the source duration: ' + str(source))
    peak = float(np.max(np.abs(samples)))
    if not 0 < peak < .75:
        raise ValueError('Unexpected decoded level: ' + str(destination))
    envelope = [round(float(np.max(np.abs(chunk))), 4) for chunk in np.array_split(samples, 96)]
    return dict(seconds=frames/rate, sample_rate=rate, channels=channels,
                peak_dbfs=round(float(20*np.log10(peak)), 2), waveform=envelope,
                sha256=digest(destination), bytes=destination.stat().st_size,
                source=dict(file=item['file'], sha256=digest(source), bytes=source.stat().st_size))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--install', action='store_true', help='Replace the repository sound collection after conversion.')
    args = parser.parse_args(); source = args.source.resolve(strict=True); output = args.output.resolve()
    if output.exists():
        raise FileExistsError('Choose a new output directory: ' + str(output))
    items = entries(source); output.parent.mkdir(parents=True, exist_ok=True)
    catalog = dict(version=2, format='mp3', sample_rate=44100, channels=2,
                   encoding=dict(codec='libmp3lame', quality=QUALITY),
                   source='Owner-supplied HyperFusion_Theme_Sounds collection', packs={})
    for item in items:
        if item['key'] == 'preview': continue
        pack = item['pack']
        catalog['packs'].setdefault(pack, dict(title=PACKS[pack][1],
            description=item['palette'].rstrip('.') + '.', events={}))
    converted = []
    with tempfile.TemporaryDirectory(prefix='.fusion-mp3-', dir=output.parent) as temp:
        staging = Path(temp) / 'collection'; staging.mkdir()
        with ThreadPoolExecutor(max_workers=4) as workers:
            for item, metadata in zip(items, workers.map(lambda item: convert(item, staging), items)):
                converted.append(dict(theme=item['theme'], event=item['event'],
                    file=str(Path(item['file']).with_suffix('.mp3')), **metadata))
                if item['key'] != 'preview':
                    catalog['packs'][item['pack']]['events'][item['key']] = metadata
        (staging / 'manifest.json').write_text(json.dumps(converted, indent=2, ensure_ascii=False) + '\n')
        (staging / 'source-manifest.json').write_bytes((source / 'manifest.json').read_bytes())
        (staging / 'README.txt').write_text(
            'HYPER FUSION THEME SOUNDS · MP3\n\n'
            '33 theme sets: eight system cues and one preview track per theme.\n'
            'LAME VBR quality 4, 44.1 kHz stereo. Original timing and levels preserved.\n'
            'The source WAV files remain in the original collection folder.\n\n'
            'Original source collection notes (WAV masters):\n\n'
            + (source / 'README.txt').read_text())
        staging.rename(output)
    if args.install:
        packs = ROOT / 'sounds/packs'; packs.mkdir(parents=True, exist_ok=True)
        # Finish the complete replacement in staging before touching current assets.
        with tempfile.TemporaryDirectory(prefix='.import-', dir=packs) as temp:
            staging = Path(temp)
            for item in items:
                if item['key'] == 'preview': continue
                path = staging / item['pack'] / (item['key'] + '.mp3')
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(output / Path(item['file']).with_suffix('.mp3'), path)
            for pack in PACKS:
                target = packs / pack; target.mkdir(exist_ok=True)
                for path in (staging / pack).glob('*.mp3'): path.replace(target / path.name)
            (staging / 'catalog.json').write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n')
            (staging / 'catalog.json').replace(packs / 'catalog.json')
            (staging / 'SOURCE.txt').write_bytes((source / 'README.txt').read_bytes())
            (staging / 'SOURCE.txt').replace(packs / 'SOURCE.txt')
            for pack in PACKS:
                for event in EVENTS:
                    (packs / pack / (event + '.ogg')).unlink(missing_ok=True)
    before = sum(item['source']['bytes'] for item in converted)
    after = sum(item['bytes'] for item in converted)
    print(json.dumps(dict(files=len(converted), themes=len(catalog['packs']),
                          wav_bytes=before, mp3_bytes=after,
                          reduction_percent=round((1-after/before)*100, 2), output=str(output)), indent=2))


if __name__ == '__main__':
    main()
