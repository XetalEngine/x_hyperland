#!/usr/bin/env python3
"""Finish a verified local deployment without replacing personal settings."""
import argparse
import json
from pathlib import Path
import sys
import install

sys.path.insert(0,str(install.PAYLOAD/'updates'))
import update_engine


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True,
                        help='Rendered release profile with its .xetal-update.json inventory')
    parser.add_argument('--profile',type=Path,default=Path.home()/'.config/hypr')
    args=parser.parse_args()
    # Check syntax, the entire compositor config and required native outputs.
    # This performs no installation, privilege elevation or session reload.
    install.validate(args.profile)
    state=Path.home()/'.local/state/xetal-hyprland/updates'
    print(json.dumps(update_engine.register_deployment(args.profile,args.reference,state),indent=2))


if __name__=='__main__':main()
