"""Archive hierarchy, literal selection and drop extraction in disposable folders."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ['DBUS_SESSION_BUS_ADDRESS']='unix:path=/nonexistent/fusion-archive-tree-tests'
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
import zipfile

from PyQt6.QtCore import QModelIndex,Qt,QUrl,QItemSelectionModel
from PyQt6.QtTest import QAbstractItemModelTester
from PyQt6.QtWidgets import QApplication

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'archive_manager'))
from engine import ArchiveError,Index,Runner
from members import MemberModel
from drag import ArchiveDrag,PATH_MIME,SERVICE_MIME,archive_identity,destination_path
from tasks import Task
import ui
from test_ui import until

APP=QApplication.instance() or QApplication([])


class TreeAndDrops(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='fusion-archive-tree-');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.enterContext(patch.dict(os.environ,{'XDG_STATE_HOME':str(self.base/'state')}))
        self.archive=self.base/'sample.zip'
        self.entries={'web/src/main.ts':'main','web/src/components/A.tsx':'component',
                      'web/public/logo.svg':'logo','web/empty/':'','README.md':'readme',
                      'odd/a*?\n雪.txt':'literal','odd/another.txt':'not selected'}
        with zipfile.ZipFile(self.archive,'w') as output:
            for path,data in self.entries.items():output.writestr(path,data)

    def task(self,request):
        result=[];task=Task(request)
        def message(event):
            if event['event']=='issue' and event['status']=='pending':
                task.command(dict(command='issue_answer',choice='replace',ids=[event['id']],versions={str(event['id']):event['version']},all=False))
        task.message.connect(message);task.outcome.connect(result.append);task.run()
        return result[0]

    def model(self):
        database=self.base/'members.sqlite'
        result=self.task(dict(operation='list',sources=[str(self.archive)],index=str(database)))
        self.assertTrue(result['ok'],result)
        model=MemberModel();model.open(database);self.addCleanup(model.close)
        return model

    def find(self,model,path):
        parent=QModelIndex()
        for name in path.split('/'):
            found=next((model.index(row,0,parent) for row in range(model.rowCount(parent)) if model.index(row,0,parent).data()==name),None)
            self.assertIsNotNone(found,path);parent=found
        return parent

    def test_implicit_folders_parent_indexes_and_sorting(self):
        model=self.model()
        tester=QAbstractItemModelTester(model,QAbstractItemModelTester.FailureReportingMode.Fatal)
        self.assertEqual(model.rowCount(),3)
        self.assertEqual(model.index(0,0).data(),'odd')
        self.assertEqual(model.index(1,0).data(),'web')
        parent=self.find(model,'web/src')
        child=self.find(model,'web/src/main.ts')
        self.assertEqual(child.parent(),parent)
        self.assertEqual(child.data(Qt.ItemDataRole.ToolTipRole),'web/src/main.ts')
        self.assertFalse(child.data(Qt.ItemDataRole.DecorationRole).isNull())
        self.assertEqual(model.rowCount(self.find(model,'web/empty')),0)
        model.sort(0,Qt.SortOrder.DescendingOrder)
        self.assertEqual(model.index(0,0).data(),'web')
        self.assertEqual(model.index(2,0).data(),'README.md')
        model.sort(1,Qt.SortOrder.DescendingOrder)
        self.assertEqual(self.find(model,'web/src/main.ts').parent(),self.find(model,'web/src'))
        del tester

    def test_search_retains_ancestors_and_selection_collapses_descendants(self):
        model=self.model()
        selected=model.selection([self.find(model,'web/src'),self.find(model,'web/src/main.ts'),self.find(model,'README.md')])
        self.assertEqual(set(selected),{'web/src','README.md'})
        model.filter('a.tsx')
        self.assertEqual(model.rowCount(),1)
        self.assertEqual(self.find(model,'web/src/components/A.tsx').data(),'A.tsx')
        self.assertEqual([i.data() for i in model.matching_folders()],['web','src','components'])
        model.filter('no-such-member');self.assertEqual(model.rowCount(),0)
        model.filter('');self.assertEqual(model.rowCount(),3)

    def test_duplicate_basenames_and_many_paged_children(self):
        database=self.base/'large.sqlite';index=Index(database)
        for folder in ['first','second']:
            for n in range(4600):index.add(dict(path=f'{folder}/{n:04}.txt',directory=False,size=n,packed=n))
        index.build_tree();index.close()
        model=MemberModel();model.open(database)
        try:
            folder=model.index(0,0)
            self.assertEqual(model.rowCount(folder),4600)
            for row in range(0,4600,257):
                item=model.index(row,0,folder)
                self.assertEqual(item.parent(),folder)
                self.assertEqual(item.data(Qt.ItemDataRole.ToolTipRole),f'first/{row:04}.txt')
            self.assertLessEqual(len(model.pages),16)
            self.assertEqual(self.find(model,'second/0000.txt').parent().data(),'second')
        finally:model.close()

    def test_dropped_file_folder_empty_directory_and_mixed_selection(self):
        cases=[(['web/src/main.ts'],{'main.ts':'main'}),
               (['web/src'],{'src/main.ts':'main','src/components/A.tsx':'component'}),
               (['web/src/main.ts','web/src/components'],{'main.ts':'main','components/A.tsx':'component'}),
               (['odd/a*?\n雪.txt'],{'a*?\n雪.txt':'literal'}),
               (['web/empty'],{})]
        before=self.archive.read_bytes()
        for n,(members,expected) in enumerate(cases):
            with self.subTest(members=members):
                destination=self.base/('drop-'+str(n))
                result=self.task(dict(operation='extract',sources=[str(self.archive)],members=members,
                                      destination=str(destination),strip_common_parent=True))
                self.assertTrue(result['ok'],result)
                files={p.relative_to(destination).as_posix():p.read_text() for p in destination.rglob('*') if p.is_file()}
                self.assertEqual(files,expected)
                if members==['web/empty']:self.assertTrue((destination/'empty').is_dir())
        self.assertEqual(self.archive.read_bytes(),before)

    def test_drop_refuses_empty_selection_and_changed_archive(self):
        request=dict(operation='extract',sources=[str(self.archive)],destination=str(self.base/'dest'),strip_common_parent=True)
        self.assertFalse(self.task(request)['ok'])
        request.update(members=['README.md'],source_identity=archive_identity(self.archive))
        with zipfile.ZipFile(self.archive,'a') as output:output.writestr('added','changed')
        self.assertFalse(self.task(request)['ok']);self.assertFalse((self.base/'dest').exists())

    def test_archive_changed_during_extraction_does_not_publish(self):
        destination=self.base/'destination';destination.mkdir()
        (destination/'README.md').write_text('existing destination')
        request=dict(operation='extract',sources=[str(self.archive)],members=['README.md'],
            destination=str(destination),strip_common_parent=True,source_identity=archive_identity(self.archive))
        original=Runner.run
        def change_after_extract(runner,arguments,**kwargs):
            result=original(runner,arguments,**kwargs)
            if arguments[0]=='x':
                with zipfile.ZipFile(self.archive,'a') as archive:archive.writestr('changed.txt','modified')
            return result
        with patch.object(Runner,'run',change_after_extract):result=self.task(request)
        self.assertFalse(result['ok']);self.assertIn('changed during extraction',result['error'])
        self.assertEqual((destination/'README.md').read_text(),'existing destination')

    def test_dropped_encrypted_and_compressed_tar_members(self):
        source=self.base/'source';(source/'nested').mkdir(parents=True)
        (source/'nested/keep.txt').write_text('selected');(source/'other.txt').write_text('unselected')
        for kind,password in [('7z','private secret'),('tar.gz',None)]:
            with self.subTest(kind=kind):
                archive=self.base/('encrypted.'+kind)
                request=dict(operation='compress',sources=[str(source)],output=str(archive),options={'format':kind,'threads':2})
                if password:request['password']=password
                self.assertTrue(self.task(request)['ok'])
                destination=self.base/('drop-'+kind)
                result=self.task(dict(operation='extract',sources=[str(archive)],members=['source/nested'],
                    destination=str(destination),password=password,strip_common_parent=True))
                self.assertTrue(result['ok'],result)
                self.assertEqual((destination/'nested/keep.txt').read_text(),'selected')
                self.assertFalse((destination/'other.txt').exists())

    def test_implicit_folder_rename_and_delete_keep_other_branches(self):
        result=self.task(dict(operation='rename',sources=[str(self.archive)],members=['web/src'],new_name='code'))
        self.assertTrue(result['ok'],result)
        with zipfile.ZipFile(self.archive) as archive:
            self.assertIn('code/components/A.tsx',archive.namelist());self.assertIn('web/public/logo.svg',archive.namelist())
        result=self.task(dict(operation='delete',sources=[str(self.archive)],members=['code']))
        self.assertTrue(result['ok'],result)
        with zipfile.ZipFile(self.archive) as archive:
            self.assertFalse(any(name.startswith('code/') for name in archive.namelist()));self.assertIn('README.md',archive.namelist())

    def test_browser_drag_survives_closing_browser_until_destination_receives_it(self):
        browser=ui.ArchiveBrowser(self.archive);browser.show()
        self.assertTrue(until(lambda:browser.model.db is not None))
        browser.reader.wait()
        target=self.find(browser.model,'web/src/main.ts')
        browser.table.selectionModel().select(target,QItemSelectionModel.SelectionFlag.ClearAndSelect|QItemSelectionModel.SelectionFlag.Rows)
        bus=Mock();bus.baseService.return_value=':1.44'
        requests=[];browser.launch.connect(requests.append)
        fake_drag=Mock();fake_drag.exec.return_value=Qt.DropAction.CopyAction
        with patch.object(ui,'ArchiveDrag',side_effect=lambda *args:ArchiveDrag(*args,bus=bus)),patch.object(ui,'QDrag',return_value=fake_drag):
            browser.start_drag()
        self.assertEqual(len(browser.pending_drops),1)
        endpoint=next(iter(browser.pending_drops.values()))
        browser.close();self.assertFalse(browser.isVisible());self.assertTrue(browser.pending_drops)
        endpoint.extractSelectedFilesTo(str(self.base))
        self.assertTrue(until(lambda:bool(requests)))
        self.assertFalse(browser.pending_drops)
        self.assertTrue(self.task(requests[0])['ok'])
        self.assertEqual((self.base/'main.ts').read_text(),'main')
        browser.deleteLater()

    def test_late_file_manager_request_after_ignore_action_still_extracts(self):
        # Wayland's QDrag result and KIO's async extraction request are separate
        # events. A delivered request must survive even an IgnoreAction result.
        browser=ui.ArchiveBrowser(self.archive);browser.show()
        self.assertTrue(until(lambda:browser.model.db is not None));browser.reader.wait()
        target=self.find(browser.model,'web/src')
        browser.table.selectionModel().select(target,QItemSelectionModel.SelectionFlag.ClearAndSelect|QItemSelectionModel.SelectionFlag.Rows)
        bus=Mock();bus.baseService.return_value=':1.45'
        requests=[];errors=[];browser.launch.connect(requests.append)
        fake_drag=Mock();fake_drag.exec.return_value=Qt.DropAction.IgnoreAction
        with patch.object(ui,'ArchiveDrag',side_effect=lambda *args:ArchiveDrag(*args,bus=bus)),patch.object(ui,'QDrag',return_value=fake_drag):
            browser.start_drag()
        try:
            self.assertEqual(len(browser.pending_drops),1)
            endpoint=next(iter(browser.pending_drops.values()));endpoint.failed.connect(errors.append)
            # Let the source's event loop continue before KIO sends its request.
            APP.processEvents();browser.close()
            endpoint.extractSelectedFilesTo(str(self.base))
            self.assertTrue(until(lambda:bool(requests)))
            self.assertEqual(errors,[]);self.assertEqual(len(requests),1)
            self.assertTrue(self.task(requests[0])['ok'])
            self.assertEqual((self.base/'src/main.ts').read_text(),'main')
            self.assertEqual((self.base/'src/components/A.tsx').read_text(),'component')
            self.assertFalse(browser.pending_drops)
            fake_drag.deleteLater.assert_not_called()
        finally:browser.close();browser.deleteLater()

    def test_request_before_drag_returns_is_not_canceled_or_repeated(self):
        for accepted in (True,False):
            with self.subTest(accepted=accepted):
                bus=Mock();bus.baseService.return_value=':1.46'
                endpoint=ArchiveDrag(self.archive,['README.md'],bus=bus);endpoint.mime_data()
                requests=[];errors=[];endpoint.launch.connect(requests.append);endpoint.failed.connect(errors.append)
                endpoint.extractSelectedFilesTo(str(self.base));APP.processEvents()
                self.assertEqual(len(requests),1);self.assertFalse(endpoint.active)
                endpoint.dropped(accepted);APP.processEvents()
                self.assertEqual(len(requests),1);self.assertEqual(errors,[])

    def test_drag_without_destination_expires_without_extracting(self):
        bus=Mock();bus.baseService.return_value=':1.47'
        endpoint=ArchiveDrag(self.archive,['README.md'],'private password',bus=bus);endpoint.mime_data()
        requests=[];closed=[];secrets=[]
        endpoint.launch.connect(requests.append)
        endpoint.closed.connect(lambda:(closed.append(True),secrets.append(endpoint.password)))
        endpoint.dropped(False)
        self.assertTrue(endpoint.active);self.assertTrue(endpoint.timer.isActive())
        endpoint.timer.start(1)
        self.assertTrue(until(lambda:bool(closed)))
        self.assertFalse(requests);self.assertEqual(secrets,[None])
        bus.unregisterObject.assert_called_once_with(endpoint.path)

    def test_drag_snapshot_private_payload_and_one_shot_request(self):
        bus=Mock();bus.isConnected.return_value=True;bus.registerObject.return_value=True;bus.baseService.return_value=':1.42'
        selection=['web/src/main.ts'];endpoint=ArchiveDrag(self.archive,selection,'private password',bus=bus)
        mime=endpoint.mime_data();self.addCleanup(endpoint.dispose)
        selection.append('README.md')
        self.assertEqual(set(mime.formats()),{SERVICE_MIME,PATH_MIME})
        self.assertFalse(mime.hasUrls())
        self.assertNotIn(b'private password',bytes(mime.data(PATH_MIME)))
        requests=[];errors=[];endpoint.launch.connect(requests.append);endpoint.failed.connect(errors.append)
        destination=self.base/'target';destination.mkdir()
        endpoint.extractSelectedFilesTo(QUrl.fromLocalFile(str(destination)).toString())
        endpoint.extractSelectedFilesTo(str(destination))
        APP.processEvents()
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0]['members'],['web/src/main.ts'])
        self.assertEqual(requests[0]['password'],'private password')
        self.assertEqual(requests[0]['destination'],str(destination))
        self.assertTrue(requests[0]['strip_common_parent']);self.assertIsNone(endpoint.password)
        self.assertTrue(errors);self.assertFalse(endpoint.active)

    def test_canceled_drag_never_extracts_and_invalid_destinations_reject(self):
        bus=Mock();bus.baseService.return_value=':1.43'
        endpoint=ArchiveDrag(self.archive,['README.md'],bus=bus);endpoint.mime_data()
        requests=[];endpoint.launch.connect(requests.append)
        endpoint.dropped(False);APP.processEvents();self.assertFalse(requests)
        for value in ('relative/path','sftp://server/path','file://remote/path','/missing-folder',''):
            with self.subTest(value=value),self.assertRaises(ArchiveError):destination_path(value)

    def test_tree_rejects_traversal_and_file_as_parent(self):
        for n,paths in enumerate([['../escape'],['file','file/child']]):
            index=Index(self.base/f'invalid-{n}.sqlite')
            try:
                for path in paths:index.add(dict(path=path,directory=False,size=1,packed=1))
                with self.assertRaises(ArchiveError):index.build_tree()
            finally:index.close()


if __name__=='__main__':unittest.main()
