#!/usr/bin/env python3
"""Run the real privileged worker inside an unprivileged disposable mount/user namespace."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]/'config/hypr'
sys.path.insert(0,str(ROOT))
from settings_profiles import archive, system


def main():
    with tempfile.TemporaryDirectory(prefix='fusion-settings-root-check-') as directory:
        base=Path(directory);etc=base/'etc';etc.mkdir();var=base/'var';var.mkdir();sysroot=base/'sys';sysroot.mkdir()
        (etc/'machine-id').write_text('isolated-settings-test')
        (etc/'hyperfusion').mkdir();settings=etc/'hyperfusion/system-tweaks.json';settings.write_text('{"version":1,"settings":{}}\n')
        stub=base/'systemctl';stub.write_text('#!/bin/sh\nprintf "fixture daemon reload\\n"\n');stub.chmod(0o755)
        command=['bwrap','--unshare-all','--die-with-parent','--new-session','--uid','0','--gid','0','--ro-bind','/','/',
                 '--bind',str(etc),'/etc','--bind',str(var),'/var/lib','--ro-bind',str(sysroot),'/sys',
                 '--tmpfs','/run','--tmpfs','/tmp','--proc','/proc','--dev','/dev',
                 '--ro-bind',str(stub),'/usr/bin/systemctl','/usr/bin/python3',str(ROOT/'settings_profiles/system.py')]
        def run(args, data=None):
            p=subprocess.run(command+args,input=data,capture_output=True,timeout=60)
            if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace'))
            return p.stdout
        document,blobs=system.unpack(run(['capture','--categories','system']))
        assert any(r['path']=='etc/hyperfusion/system-tweaks.json' for r in document['files'])
        settings.write_text('{"changed":true}\n');extra=etc/'hyperfusion/added.conf';extra.write_text('remove me')
        result=json.loads(run(['restore','--categories','system'],system.payload(document,blobs)))
        assert json.loads(settings.read_text())=={'version':1,'settings':{}}
        assert not extra.exists()
        assert result['restart_required'] is True
        assert list(var.glob('hyperfusion/settings-profiles/transactions/*/before.hfsettings'))
        assert (etc/'machine-id').read_text()=='isolated-settings-test'
        print('Privileged worker passed: capture, restore, removal, recovery archive, identity preservation; host system unchanged.')


if __name__=='__main__':main()
