#!/usr/bin/env python3
"""Stream a human-readable archive report; passwords are never journaled."""
import json
from pathlib import Path
import sys


def export(path, transfer=''):
    print('Fusion 7-Zip archive report\n')
    with open(path, encoding='utf-8') as stream:
        for line in stream:
            event = json.loads(line)
            if event['event'] == 'phase': print('\n'+event['text'])
            elif event['event'] == 'issue':
                print(f"{event['status']}: {event.get('source','')}\n  {event.get('detail','')}")
            elif event['event'] == 'result':
                print('\nResult: '+('Completed' if event.get('ok') else 'Canceled' if event.get('cancelled') else 'Failed'))
                if event.get('error'): print(event['error'])
                for note in event.get('notes',[]): print(note)
    if transfer:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'file_manager'))
        from transfer_pending import export_report
        print('\nDestination transfer details\n'); export_report(transfer,sys.stdout)


if __name__=='__main__':export(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else '')
