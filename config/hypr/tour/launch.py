#!/usr/bin/env python3
"""Open the bundled guide in the user's browser; never execute guide content."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]


def guide_url(section='home', root=ROOT):
    if section not in ('home', 'feedback', 'shortcuts'):
        raise ValueError('Unknown guide section')
    path = root / 'tour/index.html'
    if not path.is_file():
        raise FileNotFoundError('The desktop tour is missing. Reinstall the desktop guide files.')
    # Palette follows the desktop, while reading progress belongs to the browser.
    sys.path.insert(0, str(root/'theme'))
    import runtime
    query = urlencode({'theme': runtime.design(), 'mode': runtime.mode()})
    return path.as_uri() + '?' + query + '#' + section


def open_guide(section='home', environment=None):
    url = guide_url(section)
    env = dict(os.environ if environment is None else environment)
    if env.get('HYPRLAND_INSTANCE_SIGNATURE'):
        sys.path.insert(0, str(ROOT/'startup'))
        from projects_model import hide_dashboard
        hide_dashboard()
    return subprocess.Popen(['xdg-open', url], env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)


def main():
    parser = argparse.ArgumentParser(description='The Hyper Fusion desktop tour')
    parser.add_argument('--feedback', action='store_true')
    parser.add_argument('--shortcuts', action='store_true')
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT/'theme'))
    import runtime
    open_guide('feedback' if args.feedback else 'shortcuts' if args.shortcuts else 'home', runtime.environment())


if __name__ == '__main__':
    main()
