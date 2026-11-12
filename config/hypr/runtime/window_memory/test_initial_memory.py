from pathlib import Path
import json
import shlex
import subprocess
import tempfile
import unittest

from service import identity


class InitialMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.root = Path(cls.directory.name)
        cls.binary = cls.root/'initial-memory'
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'json-c', 'glib-2.0'], text=True))
        subprocess.run(['g++', '-std=c++23', '-Wall', '-Wextra', '-Werror',
                        str(Path(__file__).with_suffix('.cpp')), '-o', str(cls.binary), *flags],
                       check=True, capture_output=True, text=True, timeout=30)

    def test_native_reader_and_geometry_fit(self):
        saved = dict(floating=True, fullscreen=1, client_fullscreen=1, size=[1920,1080],
                     area=[1920,1040], floating_size=[850,600], floating_position=[120,100])
        path = self.root/'windows.json'
        path.write_text(json.dumps({'version':1, 'windows':{
            'a'*32:saved, 'b'*32:{**saved, 'floating_position':['bad',0]},
            'c'*32:{k:v for k,v in saved.items() if k!='floating_size'}}}))
        subprocess.run([str(self.binary),str(path)],check=True,capture_output=True,text=True,timeout=5)

    def test_invalid_state_is_ignored_without_aborting_a_window_map(self):
        path=self.root/'invalid.json'
        saved=dict(floating=True, fullscreen=0, client_fullscreen=0, size=[800,600], area=[1920,1080])
        bad_records=[{**saved,'floating':'true'}, {**saved,'fullscreen':3},
                     {**saved,'floating_position':[True,0]}, {**saved,'floating_size':[-1,400]},
                     {**saved,'mode_saved':1}, {**saved,'size':[float('nan'),600]}]
        documents=['{', json.dumps({'version':2,'windows':{'a'*32:saved}}),
                   json.dumps({'version':1,'windows':[]}), ' '*(4*1024*1024+1)]
        documents += [json.dumps({'version':1,'windows':{'a'*32:record}}) for record in bad_records]
        for text in documents:
            path.write_text(text)
            result=subprocess.run([str(self.binary),'read',str(path),'a'*32],capture_output=True,timeout=5)
            self.assertEqual(result.returncode,2,result.stderr)

    def test_native_identity_matches_existing_python_store(self):
        for app in ('Example.App', 'ORG.ÉDITEUR.STRASSE', 'Straße', 'xetal-file-picker-123', 'xetal-files'):
            for role,dialog in [('main',False),('0123456789abcdef',True)]:
                for transfer in (False,True) if app=='xetal-files' else (False,):
                    with self.subTest(app=app,role=role,transfer=transfer):
                        client={'class':app}
                        if transfer: client['initialTitle']='Transfer queue — Fusion Files'
                        expected=identity(client,dict(role=role,dialog=dialog))
                        actual=subprocess.check_output([str(self.binary),'identity',app,role,
                            str(int(dialog)),str(int(app.startswith('xetal-file-picker'))),str(int(transfer))],text=True)
                        self.assertEqual(actual,expected)


if __name__=='__main__':unittest.main()
