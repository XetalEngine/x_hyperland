"""Real pinned-engine and transaction checks, confined to disposable directories."""
from pathlib import Path
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'archive_manager'));sys.path.insert(0,str(ROOT))
from engine import ArchiveError, FORMATS, Index, PasswordRequired, Runner, format_arguments, list_archive
from tasks import Task
from PyQt6.QtCore import QCoreApplication, Qt


class Archives(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QCoreApplication.instance() or QCoreApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='fusion-archive-test-');self.base=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'XDG_STATE_HOME':str(self.base/'state')});self.env.start()
        self.source=self.base/'input';self.source.mkdir();self.output=self.base/'output';self.output.mkdir()
        (self.source/'hello.txt').write_bytes(b'Hello Fusion archive\n'*100)
        self.runner=Runner()
    def tearDown(self): self.env.stop();self.temp.cleanup()
    def task(self,request,choice='replace',password=None):
        task=Task(request);result=[];events=[]
        def event(value):
            events.append(value)
            if value['event']=='issue' and value['status']=='pending':
                task.command(dict(command='issue_answer',choice=choice,ids=[value['id']],versions={str(value['id']):value['version']},all=False))
            if value['event']=='password':task.command(dict(command='password',password=password))
        task.message.connect(event);task.outcome.connect(result.append);task.run()
        self.assertTrue(result);return result[0],events
    def create(self,kind='7z',**options):
        output=self.output/('sample.'+kind)
        request=dict(operation='compress',sources=[str(self.source)],output=str(output),options=dict(format=kind,threads=2,**options))
        result,events=self.task(request);self.assertTrue(result.get('ok'),result);return output

    def test_every_creation_method(self):
        for kind,(_,methods) in FORMATS.items():
            if kind.startswith('tar.'):continue
            for method in methods:
                with self.subTest(format=kind,method=method):
                    archive=self.output/(kind+'-'+method)
                    result=self.runner.run(['a',*format_arguments(dict(format=kind,method=method,threads=2)),'--',str(archive),'hello.txt'],cwd=self.source)
                    self.assertEqual(result.code,0,result.output)
                    self.assertEqual(self.runner.run(['t','--',str(archive)]).code,0)

    def test_dictionary_properties(self):
        for kind,method in [('7z','LZMA2'),('7z','LZMA'),('7z','PPMd'),('zip','LZMA'),('zip','PPMd'),('xz','LZMA2')]:
            with self.subTest(format=kind,method=method):
                archive=self.output/(kind+'-'+method)
                result=self.runner.run(['a',*format_arguments(dict(format=kind,method=method,dictionary='4m',threads=2)),'--',str(archive),'hello.txt'],cwd=self.source)
                self.assertEqual(result.code,0,result.output)

    def test_encryption_and_secret_not_in_command(self):
        import engine
        original=engine.subprocess.Popen;commands=[]
        def record(args,**kwargs):commands.append(args);return original(args,**kwargs)
        for kind,encryption in [('7z','AES256'),('zip','AES256'),('zip','ZipCrypto')]:
            secret='Sëcret with spaces\nand newline!' if kind=='7z' else 'Secret with spaces!'
            with self.subTest(format=kind,encryption=encryption),patch.object(engine.subprocess,'Popen',record):
                archive=self.output/(kind+'-'+encryption)
                result=self.runner.run(['a',*format_arguments(dict(format=kind,password=secret,encryption=encryption,threads=2)),'--',str(archive),'hello.txt'],cwd=self.source,password=secret)
                self.assertEqual(result.code,0,result.output)
                self.assertEqual(self.runner.run(['t','--',str(archive)],password=secret).code,0)
        self.assertFalse(any(secret in argument for command in commands for argument in command))

    def test_full_create_extract_and_nested_tar(self):
        (self.source/'unicode ö #\nfile.txt').write_text('literal filename')
        (self.source/'empty').mkdir()
        for kind in ('7z','zip','tar','tar.gz','tar.xz','tar.bz2','wim'):
            with self.subTest(format=kind):
                archive=self.create(kind);destination=self.base/('extracted-'+kind)
                result,_=self.task(dict(operation='extract',sources=[str(archive)],destination=str(destination)))
                self.assertTrue(result.get('ok'),result)
                self.assertEqual((destination/'input/hello.txt').read_bytes(),(self.source/'hello.txt').read_bytes())
                self.assertEqual((destination/'input/unicode ö #\nfile.txt').read_text(),'literal filename')
                self.assertTrue((destination/'input/empty').is_dir())

    def test_split_archive(self):
        (self.source/'random').write_bytes(os.urandom(80000))
        self.create('7z',volume='16k')
        parts=sorted(self.output.glob('sample.7z.*'));self.assertGreater(len(parts),1)
        result,_=self.task(dict(operation='extract',sources=[str(parts[0])],destination=str(self.base/'split')))
        self.assertTrue(result.get('ok'),result)
        self.assertEqual((self.base/'split/input/random').read_bytes(),(self.source/'random').read_bytes())

    def test_unreadable_input_is_explicit_omission(self):
        if os.getuid()==0:self.skipTest('Requires unprivileged file permissions')
        denied=self.source/'private';denied.write_text('private');denied.chmod(0)
        try:
            result,events=self.task(dict(operation='compress',sources=[str(self.source)],output=str(self.output/'partial.7z'),options={'format':'7z'}),choice='skip')
            self.assertTrue(result.get('ok'),result);self.assertTrue(result['notes'])
            self.assertTrue(any(e['event']=='issue' and e['status']=='skipped' for e in events))
        finally:denied.chmod(0o600)

    def test_overwrite_skip_keeps_existing_archive(self):
        archive=self.create('zip');before=archive.read_bytes();(self.source/'new').write_text('new')
        result,events=self.task(dict(operation='compress',sources=[str(self.source)],output=str(archive),options={'format':'zip'}),choice='skip')
        self.assertTrue(result.get('ok'),result);self.assertEqual(archive.read_bytes(),before);self.assertTrue(result['notes'])

    def test_reject_escaping_paths_without_touching_destination(self):
        for member in ('../escape.txt','/absolute.txt','C:/windows.txt','safe/../../escape.txt'):
            with self.subTest(member=member):
                archive=self.output/'bad.zip'
                with zipfile.ZipFile(archive,'w') as out:out.writestr(member,'bad')
                destination=self.base/'dest';destination.mkdir(exist_ok=True);(destination/'keep').write_text('original')
                result,_=self.task(dict(operation='extract',sources=[str(archive)],destination=str(destination)))
                self.assertFalse(result['ok']);self.assertEqual(sorted(p.name for p in destination.iterdir()),['keep'])

    def test_reject_link_parent(self):
        index=Index(self.base/'links.sqlite')
        for item in [dict(path='link',directory=False,size=0,packed=0,symlink='real'),dict(path='link/child',directory=False,size=1,packed=1)]:index.add(item)
        with self.assertRaises(ArchiveError):index.validate()
        index.close()

    def test_zip_symlink_cannot_write_outside_staging(self):
        import stat
        outside=self.base/'outside';outside.mkdir();(outside/'keep').write_text('original')
        archive=self.output/'unsafe-link.zip'
        link=zipfile.ZipInfo('link');link.create_system=3;link.external_attr=(stat.S_IFLNK|0o777)<<16
        with zipfile.ZipFile(archive,'w') as output:
            output.writestr(link,str(outside));output.writestr('link/escape','must not escape')
        result,_=self.task(dict(operation='extract',sources=[str(archive)],destination=str(self.base/'destination')))
        self.assertFalse(result['ok']);self.assertEqual(sorted(p.name for p in outside.iterdir()),['keep'])

    def test_socket_is_omitted_but_ordinary_sock_file_is_preserved(self):
        import socket
        sock=socket.socket(socket.AF_UNIX)
        try:
            try:sock.bind(str(self.source/'runtime.sock'))
            except PermissionError:self.skipTest('Socket creation requires an unsandboxed disposable test directory')
            (self.source/'ordinary.sock').write_text('real file data')
            for kind in ('7z','zip','tar.gz'):
                archive=self.create(kind)
                destination=self.base/('socket-'+kind)
                result,events=self.task(dict(operation='extract',sources=[str(archive)],destination=str(destination)))
                self.assertTrue(result['ok'],result)
                self.assertEqual((destination/'input/ordinary.sock').read_text(),'real file data')
                self.assertFalse((destination/'input/runtime.sock').exists())
                self.assertFalse(any(e['event']=='issue' for e in events))
        finally:sock.close()

    def test_corrupt_archive_preserves_target(self):
        archive=self.output/'broken.7z';archive.write_bytes(b'7z\xbc\xaf\x27\x1c'+b'broken'*30)
        dest=self.base/'keep';dest.mkdir();(dest/'important').write_text('keep')
        result,_=self.task(dict(operation='extract',sources=[str(archive)],destination=str(dest)))
        self.assertFalse(result['ok']);self.assertEqual((dest/'important').read_text(),'keep')

    def test_selected_members_literal_wildcards(self):
        (self.source/'literal*.txt').write_text('star');(self.source/'literal-other.txt').write_text('other')
        archive=self.create('zip');dest=self.base/'selected'
        result,_=self.task(dict(operation='extract',sources=[str(archive)],destination=str(dest),members=['input/literal*.txt']))
        self.assertTrue(result.get('ok'),result);self.assertEqual((dest/'input/literal*.txt').read_text(),'star')
        self.assertFalse((dest/'input/literal-other.txt').exists())

    def test_selected_input_filename_is_not_a_search_pattern(self):
        selected=self.source/'name*.txt';selected.write_text('selected file')
        (self.source/'name-other.txt').write_text('not selected')
        archive=self.output/'literal.zip'
        result,_=self.task(dict(operation='compress',sources=[str(selected)],output=str(archive),options={'format':'zip'}))
        self.assertTrue(result['ok'],result)
        with zipfile.ZipFile(archive) as z:self.assertEqual(z.namelist(),['name*.txt'])

    def test_update_delete_rename(self):
        archive=self.create('zip');extra=self.base/'extra.txt';extra.write_text('added')
        result,_=self.task(dict(operation='add',sources=[str(archive)],add=[str(extra)]));self.assertTrue(result.get('ok'),result)
        result,_=self.task(dict(operation='rename',sources=[str(archive)],members=['extra.txt'],new_name='renamed.txt'));self.assertTrue(result.get('ok'),result)
        result,_=self.task(dict(operation='delete',sources=[str(archive)],members=['input/hello.txt']));self.assertTrue(result.get('ok'),result)
        with zipfile.ZipFile(archive) as output:
            self.assertEqual(output.read('renamed.txt'),b'added');self.assertNotIn('input/hello.txt',output.namelist())

    def test_cancel_before_start_creates_nothing(self):
        task=Task(dict(operation='compress',sources=[str(self.source)],output=str(self.output/'cancel.zip'),options={'format':'zip'}))
        results=[];task.outcome.connect(results.append);task.command({'command':'cancel'});task.run()
        self.assertTrue(results[0].get('cancelled'));self.assertFalse((self.output/'cancel.zip').exists())

    def test_new_nested_destination_is_published_by_transfer_worker(self):
        archive=self.output/'new/nested/sample.zip'
        result,_=self.task(dict(operation='compress',sources=[str(self.source)],output=str(archive),options={'format':'zip'}))
        self.assertTrue(result['ok'],result)
        destination=self.base/'extract/new/nested'
        result,_=self.task(dict(operation='extract',sources=[str(archive)],destination=str(destination),separate=True))
        self.assertTrue(result['ok'],result)
        self.assertEqual((destination/'sample/input/hello.txt').read_bytes(),(self.source/'hello.txt').read_bytes())

    def test_pause_resume_and_cancel_running_engine_keeps_existing_output(self):
        import threading
        import time
        (self.source/'random').write_bytes(os.urandom(32*1024*1024))
        archive=self.output/'cancel.7z';archive.write_bytes(b'existing archive')
        task=Task(dict(operation='compress',sources=[str(self.source)],output=str(archive),options={'format':'7z','threads':1}))
        result=[];task.outcome.connect(result.append,Qt.ConnectionType.DirectConnection)
        worker=threading.Thread(target=task.run);worker.start()
        try:
            deadline=time.monotonic()+10
            while task.control.process is None and worker.is_alive() and time.monotonic()<deadline:time.sleep(.01)
            self.assertIsNotNone(task.control.process)
            task.command({'command':'pause'})
            time.sleep(.1)
            self.assertTrue(task.control.paused);self.assertTrue(worker.is_alive())
            task.command({'command':'resume'})
            self.assertFalse(task.control.paused)
            task.command({'command':'cancel'});worker.join(10)
            self.assertFalse(worker.is_alive());self.assertTrue(result[0].get('cancelled'),result)
            self.assertEqual(archive.read_bytes(),b'existing archive')
        finally:
            task.command({'command':'cancel'});worker.join(10)


if __name__=='__main__':unittest.main()
