#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop_services.phone import whatsapp_url

if __name__=='__main__':
    try:
        if len(sys.argv)>2:raise ValueError('Provide one WhatsApp link.')
        url=whatsapp_url(sys.argv[1] if len(sys.argv)==2 else '')
        raise SystemExit(subprocess.call(['xdg-open',url]))
    except ValueError as error:
        print(str(error),file=sys.stderr);raise SystemExit(2)
