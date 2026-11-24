#!/usr/bin/env python3
"""Session activation and foreground package restore entry points."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from settings_profiles import archive, audio, backend, packages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('activate', 'audio', 'packages'))
    parser.add_argument('path', nargs='?', type=Path)
    args = parser.parse_args()
    if args.action == 'activate': return 20 if backend.activate() else 0
    if args.action == 'audio':
        path = ROOT/'settings_profiles/audio.json'
        if path.exists():
            value = json.loads(path.read_text())
            for attempt in range(20):
                try: audio.restore(value); path.unlink(); return 0
                except RuntimeError:
                    if attempt == 19: raise
                    time.sleep(.5)
        return 0
    if not args.path or args.path.is_symlink(): raise ValueError('Missing package operation directory.')
    try:
        wanted = json.loads((args.path/'wanted.json').read_text())
        print('Restore installed applications\nReview any package-manager prompts here.\n', flush=True)
        report = packages.apply(wanted, backend.administrator)
        result = {'ok': True, **report}
    except BaseException as error:
        result = {'ok': False, 'error': str(error)}
        print('\nApplication restore stopped: ' + str(error), file=sys.stderr, flush=True)
    archive.atomic(args.path/'result.json', archive.encode(result))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as error:
        print('Default Settings: ' + str(error), file=sys.stderr); raise SystemExit(1)
