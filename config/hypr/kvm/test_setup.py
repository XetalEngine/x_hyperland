"""First-run and close regressions in an isolated workspace; never starts a VM."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch,Mock

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import portable


class SetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='kvm-setup-test-')
        cls.environment=patch.dict(os.environ,{'XETAL_KVM_DATA':cls.temporary.name})
        cls.environment.start()
        portable.prepare()
        import app
        cls.kvm=app
        cls.application=app.QApplication.instance() or app.QApplication([])
        cls.application.setQuitOnLastWindowClosed(False)
        app.desktop_theme.install(cls.application,app.backend_theme.build_stylesheet('#65d5cb'))

    @classmethod
    def tearDownClass(cls):
        cls.environment.stop();cls.temporary.cleanup()

    def setUp(self):
        import editions
        for name, value in (('host_address','192.168.50.10'), ('username','alice')):
            discovery=patch('guest_connection.'+name, return_value=value)
            discovery.start();self.addCleanup(discovery.stop)
        # Most UI fixtures have no component download service. Dedicated module
        # tests below enable preparation with a local fake download.
        optional=patch('module_policy.requested',return_value=False)
        optional.start();self.addCleanup(optional.stop)
        editions.select('stock')
        from model import VMConfig
        for profile in ('windows','macos'):
            path=self.kvm.vmstart2.profiles.paths(portable.data_root(),profile).session
            VMConfig(portable.configuration(profile)).save(path)
        self.kvm.vmstart2.profiles.remember(portable.data_root(),'windows')
        self.window=self.kvm.KVMSettings();self.window.show()
        self.application.processEvents()

    def tearDown(self):
        self.window.tabs.blockSignals(True);self.window.tab_wizard.blockSignals(True)
        self.window.hide();self.window.deleteLater()
        self.application.sendPostedEvents(None,self.kvm.QEvent.Type.DeferredDelete)

    def test_downloads_first_and_one_panel_survives_navigation(self):
        w=self.window;wizard=w.tab_wizard;panel=w.package_panel
        self.assertEqual(wizard.steps[wizard.step][0],'components')
        self.assertEqual(panel.table.rowCount(),6)
        self.assertEqual(panel.store.edition,'stock')
        self.assertNotIn('kvm-amd',panel.release['components'])
        self.assertIs(panel.parentWidget(),wizard.component_host)
        self.assertFalse(w._components_ready())
        w._select_tab_by_name('Paths & Tools')
        self.assertIs(panel.parentWidget(),w.tab_paths.widget())
        w._select_tab_by_name('Wizard');wizard.go(1)
        self.assertIs(panel.parentWidget(),w.tab_paths.widget())
        wizard.go(0)
        self.application.sendPostedEvents(None,self.kvm.QEvent.Type.DeferredDelete)
        self.assertIs(panel.parentWidget(),wizard.component_host)
        self.assertEqual(panel.table.rowCount(),6)

    def test_close_saves_without_a_confirmation_or_applying_opencore(self):
        from PyQt6.QtWidgets import QMessageBox
        self.window.cfg.simple['name']='saved automatically'
        with patch.object(QMessageBox,'question',side_effect=AssertionError('Close asked a question')):
            self.assertTrue(self.window.close())
        self.assertFalse(self.window.isVisible())
        saved=json.loads(self.window._paths().session.read_text())
        self.assertEqual(saved['simple']['name'],'saved automatically')
        self.assertTrue(Path(str(self.window._paths().session)+'.prev').is_file())

    def test_disk_card_edits_survive_refresh_save_and_reopen(self):
        from PyQt6.QtWidgets import QFileDialog,QMessageBox
        from model import VMConfig
        import editions
        import virtual_gpu
        w=self.window
        first=portable.data_root()/'old-installer.iso';first.write_bytes(bytes(4096))
        replacement=portable.data_root()/'new-installer.iso';replacement.write_bytes(bytes(4096))
        typed=portable.data_root()/'typed-installer.iso';typed.write_bytes(bytes(4096))
        def emitted(cfg,flag):
            argv=cfg.to_argv()
            return [json.loads(argv[i+1]) for i,value in enumerate(argv[:-1]) if value==flag]
        def saved():
            w.btn_save.click()
            self.assertFalse(w.is_modified())
            return VMConfig.load(w._paths().session,root=w._paths().root)
        def reopen():
            # The same read/rebuild path used when opening saved settings.
            w.cfg=w._read_profile(w.profile_id);w._rebuild_tabs()
        with patch.object(virtual_gpu,'service_active',return_value=False), \
             patch.object(QMessageBox,'critical',side_effect=AssertionError('Unexpected save failure')):
            for profile in ('windows','macos'):
                w.switch_profile(profile)
                for edition in ('stock','xetallic'):
                    with self.subTest(profile=profile,edition=edition):
                        editions.select(edition);w._refresh_all()
                        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(first),'')):
                            w.tab_disks.add_iso()
                        row=next(r for r in w.tab_disks.rows if r.bd.get('filename')==str(first))
                        node,device_id=row.bd['node-name'],row.dev['id']
                        # Save and repeated refreshes must leave the card bound
                        # to the configuration used by the command and writer.
                        saved();w._refresh_all();w._refresh_all()
                        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(replacement),'')):
                            row._browse()
                        self.assertTrue(w.is_modified())
                        self.assertEqual(next(b['filename'] for b in emitted(saved(),'-blockdev')
                                              if b.get('node-name')==node),str(replacement))
                        self.assertIn(str(replacement),w.preview.toPlainText())
                        reopen()
                        row=next(r for r in w.tab_disks.rows if r.dev.get('id')==device_id)
                        self.assertEqual(row.path.currentText(),str(replacement))
                        row.path.setEditText(str(typed))
                        row.path.lineEdit().textEdited.emit(str(typed))
                        self.assertEqual(next(b['filename'] for b in emitted(saved(),'-blockdev')
                                              if b.get('node-name')==node),str(typed))
                        row.active.click()
                        loaded=saved()
                        self.assertNotIn(node,{b.get('node-name') for b in emitted(loaded,'-blockdev')})
                        self.assertNotIn(device_id,{d.get('id') for d in emitted(loaded,'-device')})
                        reopen()
                        row=next(r for r in w.tab_disks.rows if r.dev.get('id')==device_id)
                        self.assertFalse(row.active.isChecked())
                        row.active.click();loaded=saved()
                        self.assertIn(node,{b.get('node-name') for b in emitted(loaded,'-blockdev')})
                        row=next(r for r in w.tab_disks.rows if r.dev.get('id')==device_id)
                        row.btn_remove.click();loaded=saved()
                        self.assertNotIn(node,{b.get('node-name') for b in loaded.blockdevs})
                        self.assertNotIn(device_id,{d.get('id') for d in loaded.devices})
                        reopen()
                        self.assertFalse(any(r.dev.get('id')==device_id for r in w.tab_disks.rows))

    def test_account_header_is_before_save_on_every_page(self):
        import account_ui
        header=self.window.account_header
        actions=self.window.account_actions.layout()
        self.assertEqual(actions.indexOf(header)+1,actions.indexOf(self.window.btn_save))
        for page in ('Paths & Tools','Virtual GPU','Single GPU','Dual GPU'):
            self.window._select_tab_by_name(page)
            self.application.processEvents()
            self.assertTrue(header.isVisible());self.assertTrue(header.login.isVisible())
            self.assertFalse(header.logout.isVisible())
        with patch.object(account_ui.QDesktopServices,'openUrl',return_value=True) as open_url:
            header.download.click()
        self.assertEqual(open_url.call_args.args[0].toString(),account_ui.SITE+'/#download')
        for width in (1820,1280,800,1820):
            self.window.resize(width,920);self.application.processEvents()
            self.assertLess(header.geometry().right(),self.window.btn_save.geometry().left())
            self.assertGreaterEqual(self.window.account_actions.x(),0)
            self.assertLessEqual(self.window.account_actions.geometry().right(),self.window.width())
            self.assertEqual(self.window._account_wrapped,width<1540)

    def test_header_login_and_logout_while_guest_is_running(self):
        from account_ui import LoginDialog
        import echo_account
        panel=self.window.package_panel;header=self.window.account_header
        def accept(dialog):
            dialog.login.setText('test-user');dialog.password.setText('fixture-password')
            return LoginDialog.DialogCode.Accepted
        with patch.object(echo_account.shutil,'which',return_value=None), \
             patch.object(echo_account,'request',return_value={'token':'fixture-token','user':{'username':'test-user'}}) as request, \
             patch.object(LoginDialog,'exec',accept):
            header.login.click();self.wait_for_components(panel)
            self.assertEqual(header.status.text(),'Logged in as test-user')
            self.assertTrue(header.logout.isVisible());self.assertFalse(header.login.isVisible())
            request.assert_called_once_with('login',{'login':'test-user','password':'fixture-password','totp':''})
            with patch.object(panel,'busy',return_value=True):
                header.logout.click();self.wait_for_components(panel)
        self.assertFalse(panel.account.token)
        self.assertTrue(header.login.isVisible());self.assertFalse(header.logout.isVisible())

    def test_failed_login_is_visible_from_launch_page(self):
        from account_ui import LoginDialog
        import echo_account
        self.window._select_tab_by_name('Virtual GPU')
        panel=self.window.package_panel
        def accept(dialog):
            dialog.login.setText('test-user');dialog.password.setText('fixture-password')
            return LoginDialog.DialogCode.Accepted
        with patch.object(echo_account.shutil,'which',return_value=None), \
             patch.object(echo_account,'request',side_effect=echo_account.AccountError('Sign in to Echo again to continue.',status=401)), \
             patch.object(LoginDialog,'exec',accept):
            self.window.account_header.login.click();self.wait_for_components(panel)
        self.assertEqual(self.window.status.text(),'Sign in to Echo again to continue.')
        self.assertFalse(panel.account.token);self.assertTrue(self.window.account_header.login.isVisible())

    def test_close_reopen_requires_login_and_saves_no_account_in_profile(self):
        panel=self.window.package_panel;account=panel.account
        account.token='fixture-secret-token';account.user={'username':'test-user'};panel.refresh_account()
        self.assertTrue(self.window.save_session(quiet=True))
        saved=self.window._paths().session.read_text()
        self.assertNotIn('fixture-secret-token',saved);self.assertNotIn('test-user',saved)
        self.window.close();self.window.show_for_session();self.application.processEvents()
        self.assertEqual((account.token,account.user),('',{}))
        self.assertTrue(self.window.account_header.login.isVisible())
        panel.store.edition='xetallic'
        with patch.object(panel,'sign_in') as prompt:
            self.assertFalse(panel.require_account());prompt.assert_called_once_with()
        panel.store.edition='stock'
        with patch.object(panel,'sign_in') as prompt:
            self.assertTrue(panel.require_account());prompt.assert_not_called()

    def test_pending_login_does_not_survive_close_and_reopen(self):
        import echo_account
        panel=self.window.package_panel;started=threading.Event();release=threading.Event();after=Mock()
        session=panel.account.session
        def pending(*args,**kwargs):
            started.set();release.wait(5)
            return {'token':'fixture-token','user':{'username':'test-user'}}
        with patch.object(echo_account,'request',side_effect=pending), \
             patch.object(echo_account.shutil,'which',return_value=None):
            panel.run(lambda progress:panel.account.login('test-user','fixture-password',session=session),
                      lambda user:panel.info.setText('Signed in.'),after=after,session=session)
            try:
                self.assertTrue(started.wait(5))
                self.window.close();self.window.show_for_session()
            finally:release.set();self.wait_for_components(panel)
        self.application.processEvents()
        self.assertFalse(panel.account.token);self.assertEqual(panel.account.user,{})
        self.assertTrue(self.window.account_header.login.isVisible());after.assert_not_called()

    def test_saved_password_prefills_but_cancel_does_not_authenticate(self):
        from account_ui import LoginDialog
        import echo_account
        panel=self.window.package_panel;shown=[]
        def cancel(dialog):
            self.assertFalse(panel.account.token)
            self.assertEqual(dialog.login.text(),'test-user')
            self.assertEqual(dialog.password.text(),'fixture-password')
            self.assertTrue(dialog.remember.isChecked());self.assertEqual(dialog.totp.text(),'')
            shown.append(True)
            return LoginDialog.DialogCode.Rejected
        with patch.object(echo_account.shutil,'which',return_value='/fixture/secret-tool'), \
             patch.object(panel.account,'saved_credentials',return_value={'login':'test-user','password':'fixture-password'}), \
             patch.object(LoginDialog,'exec',cancel),patch.object(echo_account,'request') as request:
            self.window.account_header.login.click();self.wait_for_components(panel)
            self.application.processEvents()
        self.assertEqual(shown,[True]);self.assertFalse(panel.account.token);request.assert_not_called()

    def test_edition_buttons_preserve_guest_state_and_block_busy_switches(self):
        import editions,packages
        panel=self.window.package_panel;cfg=self.window.cfg.data
        nvram=portable.data_root()/'firmware/OVMF_VARS.fd';nvram.write_bytes(b'private guest state')
        previous=copy.deepcopy(cfg['smbios'])
        inventories={edition:packages.decode((portable.ROOT/filename).read_bytes())['components']
                     for edition,filename in [('stock','catalog-stock.json'),('xetallic','catalog.json')]}
        with patch.object(packages,'installed',side_effect=lambda name,root=None:inventories[root.name if root else editions.selected()].get(name,{})), \
             patch.object(panel,'busy',return_value=False):
            self.assertEqual(panel.edition_buttons['xetallic'].text(),'Switch to Enhanced')
            panel.choose_edition('xetallic')
            self.assertEqual(editions.selected(),'xetallic')
            self.assertEqual(panel.table.rowCount(),7)
            self.assertFalse(panel.account_button.isHidden())
            self.assertIn('/editions/xetallic/',cfg['_meta']['binary'])
            self.assertFalse(panel.edition_buttons['max'].isEnabled())
            self.assertEqual(panel.edition_buttons['stock'].text(),'Switch to Basic')
            with patch.object(panel,'busy',return_value=True):
                panel.choose_edition('stock');self.assertEqual(editions.selected(),'xetallic')
            panel.choose_edition('stock')
            self.assertEqual(panel.table.rowCount(),6)
            self.assertTrue(panel.account_button.isHidden())
        self.assertEqual(nvram.read_bytes(),b'private guest state')
        self.assertEqual(cfg['smbios'],previous)

    def wait_for_components(self,panel):
        deadline=time.monotonic()+5
        while panel.job and time.monotonic()<deadline:
            self.application.processEvents();time.sleep(.01)
        self.assertIsNone(panel.job)

    def test_failed_preparation_keeps_current_edition_and_profile(self):
        import editions,packages
        panel=self.window.package_panel;panel.account.token='test token'
        previous=copy.deepcopy(self.window.cfg.data)
        with patch.object(panel,'busy',return_value=False), \
             patch.object(packages.Store,'check',side_effect=OSError('download unavailable')):
            panel.choose_edition('xetallic')
            self.wait_for_components(panel)
        self.assertEqual(editions.selected(),'stock')
        self.assertEqual(panel.store.edition,'stock')
        self.assertEqual(self.window.cfg.data,previous)
        self.assertIn('download unavailable',panel.info.text())

    def test_preparation_finishes_before_selection_and_saves_it(self):
        import editions,packages
        panel=self.window.package_panel;panel.account.token='test token'
        release=packages.decode((portable.ROOT/'catalog.json').read_bytes())
        calls=[]
        def download(store,name,entry,progress):
            self.assertEqual(editions.selected(),'stock')
            self.assertEqual(store.edition,'xetallic');calls.append(name)
        with patch.object(panel,'busy',return_value=False), \
             patch.object(packages.Store,'check',return_value=release), \
             patch.object(packages.Store,'download',autospec=True,side_effect=download):
            panel.choose_edition('xetallic');self.wait_for_components(panel)
        self.assertIn('qemu',calls);self.assertIn('ovmf',calls)
        self.assertEqual(editions.selected(),'xetallic')
        self.assertEqual(panel.store.edition,'xetallic')
        saved=json.loads(self.window._paths().session.read_text())
        self.assertEqual(saved['_meta']['vm_edition'],'xetallic')

    def test_failed_switch_does_not_change_visible_selection(self):
        import editions,packages
        panel=self.window.package_panel
        with patch.object(panel,'switch_edition',side_effect=OSError('save failed')), \
             patch.object(panel,'busy',return_value=False):
            panel._commit_edition(packages.Store(edition='xetallic'),panel.release)
        self.assertEqual(editions.selected(),'stock')
        self.assertEqual(panel.store.edition,'stock')
        self.assertIn('save failed',panel.info.text())

    def test_close_during_download_hides_then_allows_the_job_to_finish(self):
        gate=threading.Event();finished=[]
        panel=self.window.package_panel
        panel.run(lambda progress:gate.wait(5),finished.append)
        start=time.monotonic()
        self.assertTrue(self.window.close())
        self.assertLess(time.monotonic()-start,1)
        self.assertFalse(self.window.isVisible())
        gate.set()
        deadline=time.monotonic()+5
        while panel.job and time.monotonic()<deadline:
            self.application.processEvents();time.sleep(.01)
        self.assertIsNone(panel.job)
        self.assertEqual(finished,[True])

    def test_same_gpu_and_pinning_keep_captured_options(self):
        from tabs_wizard import WizardTab
        from model import VMConfig
        import hostinfo
        cfg=VMConfig(portable.configuration('windows'))
        wizard=WizardTab(cfg)
        before=copy.deepcopy(cfg.data['pinning'])
        wizard.go(4)  # CPU cores, after Downloads/vendor/IOMMU/memory.
        # A suggested map equal to the captured map must not reset RT throttling.
        suggested={k:copy.deepcopy(before[k]) for k in ('vcpus','guest_cores','vcpupin','emulatorpin','iothreadpin')}
        suggested['host_cores']=[]
        with patch.object(hostinfo,'suggest_pinning',return_value=suggested):
            wizard._apply_pinning()
        self.assertEqual(cfg.data['pinning'],before)
        cfg.devices.extend([
            {'driver':'vfio-pci','id':'fixture-gpu','host':'0000:01:00.0','romfile':'/fixture/gpu.rom','x-vga':True},
            {'driver':'vfio-pci','id':'fixture-audio','host':'0000:01:00.1'},
        ])
        devices=copy.deepcopy(cfg.devices)
        active=[d for d in cfg.devices if d.get('driver')=='vfio-pci' and not d.get('_disabled')]
        slot=active[0]['host']
        wizard.host_gpus=[dict(slot=slot,functions=[{'slot':d['host']} for d in active
                                                  if d['host'].rsplit('.',1)[0]==slot.rsplit('.',1)[0]])]
        wizard._apply_gpu(slot,active[0].get('romfile',''))
        self.assertEqual(cfg.devices,devices)
        wizard.deleteLater()

    def test_skipping_disks_keeps_mac_boot_and_support_media(self):
        from tabs_wizard import WizardTab
        from model import VMConfig
        cfg=VMConfig(portable.configuration('macos'))
        kept=[copy.deepcopy(b) for b in cfg.blockdevs if b.get('filename','').endswith(('.img','.iso','.fd'))]
        wizard=WizardTab(cfg);wizard.disk_rows=[]
        wizard._reconcile_host_disks();wizard._apply_drives()
        for block in kept:
            self.assertIn(block,cfg.blockdevs)
            self.assertFalse(block.get('_disabled'))
        for block in cfg.blockdevs:
            if block.get('filename','').startswith('/dev/'):self.assertTrue(block.get('_disabled'))
        wizard.deleteLater()

    def test_wizard_stays_out_of_sidebar(self):
        self.window._open_wizard()
        self.assertIs(self.window.tabs.currentWidget(),self.window.tab_wizard)
        self.assertTrue(self.window.navigation.items['Wizard'].isHidden())

    def test_finish_offers_nat_when_recipient_has_no_baseline_bridge(self):
        import hostinfo
        wizard=self.window.tab_wizard
        before=copy.deepcopy(self.window.cfg.data)
        with patch.object(hostinfo,'net_bridges',return_value=[]):wizard.go(len(wizard.steps)-1)
        self.assertTrue(wizard.use_nat.isChecked())
        self.assertEqual(self.window.cfg.data['network'],before['network'])
        wizard.next_action()
        self.assertEqual(self.window.cfg.network['mode'],'user')
        self.assertEqual(json.loads(self.window.cfg.simple['netdev'])['type'],'user')
        self.assertEqual(json.loads(self.window.cfg.simple['netdev'])['id'],json.loads(before['simple']['netdev'])['id'])

    def test_finish_preserves_available_bridge(self):
        import hostinfo
        wizard=self.window.tab_wizard;before=copy.deepcopy(self.window.cfg.data['network'])
        with patch.object(hostinfo,'net_bridges',return_value=[before['bridge']]):wizard.go(len(wizard.steps)-1)
        self.assertIsNone(wizard.use_nat)
        wizard.next_action()
        self.assertEqual(self.window.cfg.data['network'],before)

    def test_create_bridge_selects_it_for_wizard_and_all_launch_modes(self):
        import hostinfo, network_bridge
        from network_config import configure
        w = self.window
        with patch.object(hostinfo,'net_bridges',return_value=[]):
            w.tab_wizard.go(len(w.tab_wizard.steps)-1)
            self.assertTrue(w.tab_wizard.use_nat.isChecked())
            self.assertEqual(w.tab_wizard.btn_create_bridge.text(),'Create Bridge')
        calls=[]
        def run(work, done, failed=None):
            calls.append('run');done(work(lambda *_:None))
        with patch.object(w,'_busy',return_value=False), patch.object(w.package_panel,'run',side_effect=run), \
             patch.object(network_bridge,'request',return_value={'bridge':'br0','message':'Bridge ready'}) as request, \
             patch.object(hostinfo,'net_bridges',return_value=['br0']):
            w.tab_wizard.btn_create_bridge.click()
        request.assert_called_once_with('br0')
        self.assertIsNone(w.tab_wizard.use_nat)
        self.assertFalse(w.tab_machine.btn_create_bridge.isVisible())
        self.assertEqual(w.cfg.network['bridge'],'br0')
        argv=w.cfg.to_argv(True);netdev=json.loads(argv[argv.index('-netdev')+1])
        self.assertEqual(netdev['type'],'tap')
        self.assertEqual(netdev['ifname'],w.cfg.network['ifname'])
        self.assertNotIn('fd',netdev)
        mac=next(d['mac'] for d in w.cfg.devices if d.get('netdev'))
        w.tab_machine.net_mode.setCurrentIndex(w.tab_machine.net_mode.findData('user'))
        self.assertEqual(w.cfg.network['mode'],'user')
        self.assertEqual(next(d['mac'] for d in w.cfg.devices if d.get('netdev')),mac)
        self.assertEqual(json.loads(w.cfg.simple['netdev'])['type'],'user')

    def test_bridge_creation_is_blocked_while_guest_is_running(self):
        import network_bridge
        with patch.object(self.window,'_busy',return_value=True), patch.object(network_bridge,'request') as request:
            self.window._create_bridge('br0')
        request.assert_not_called()
        self.assertIn('shut down the VM',self.window.status.text())

    def test_guest_script_preview_and_copy_work_before_module_download(self):
        w = self.window
        self.assertFalse(portable.component_path('kvm-amd').exists())
        # Upgrade a saved preset with the previous managed component path.
        w.cfg.data['tools']['vmstealth_guest'] = str(portable.component_path('kvm-amd')/'vmstealth75.bat')
        w.cfg.data['tools']['vmstealth_host'] = str(portable.component_path('kvm-amd')/'vmstealth75.sh')
        tab = w.tab_paths
        tab.tools(); tab.refresh()
        self.assertTrue(Path(w.cfg.data['tools']['vmstealth_guest']).is_file())
        self.assertEqual(w.cfg.data['tools']['vmstealth_host'], str(portable.ROOT/'guest/vmstealth75.sh'))
        self.assertTrue(tab.guest_batch_copy.isEnabled())
        self.assertIn('set "HOST_LOGIN=alice@192.168.50.10"', tab.guest_batch_preview.toPlainText())
        self.assertIn('set "GUEST_NAME=win10"', tab.guest_batch_preview.toPlainText())
        tab.guest_batch_copy.click()
        self.assertEqual(self.application.clipboard().text(), tab._guest_batch_text)
        self.assertIn('HOST_LOGIN', self.application.clipboard().text())

    def test_local_ssh_button_runs_setup_with_a_running_vm_and_refreshes_copy(self):
        import local_ssh
        w = self.window; tab = w.tab_paths
        def run(work, done, failed): done(work(lambda *_:None))
        with patch.object(w, '_busy', return_value=True), patch.object(w.package_panel, 'run', side_effect=run), \
             patch.object(local_ssh, 'request', return_value={'message':'Local SSH ready','port':2222}) as request:
            tab.guest_ssh_enable.click()
        request.assert_called_once_with()
        self.assertEqual(tab.guest_ssh_enable.text(), 'Local SSH enabled')
        self.assertEqual(tab.guest_ssh_status.text(), 'Local SSH ready')
        tab.guest_batch_copy.click()
        self.assertIn('set "HOST_PORT=2222"', self.application.clipboard().text())

    def test_local_ssh_cancellation_is_visible_and_can_be_retried(self):
        w = self.window; tab = w.tab_paths
        def run(work, done, failed): failed('Authentication was cancelled.')
        with patch.object(w.package_panel, 'run', side_effect=run): tab.guest_ssh_enable.click()
        self.assertEqual(tab.guest_ssh_enable.text(), 'Enable local SSH')
        self.assertIn('cancelled', tab.guest_ssh_status.text())

    def test_local_ssh_authentication_worker_keeps_the_ui_responsive(self):
        import local_ssh
        from PyQt6.QtCore import QTimer
        from PyQt6.QtTest import QTest
        release=threading.Event(); ticks=[]
        timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(True));timer.start()
        def request():
            release.wait(3)
            return {'message':'Local SSH ready','port':2222}
        try:
            with patch.object(local_ssh,'request',side_effect=request):
                self.window.tab_paths.guest_ssh_enable.click()
                QTest.qWait(100)
                self.assertFalse(self.window.tab_paths.guest_ssh_enable.isEnabled())
                self.assertGreaterEqual(len(ticks),3)
                release.set()
                for _ in range(200):
                    if self.window.package_panel.job is None:break
                    QTest.qWait(10)
                self.assertIsNone(self.window.package_panel.job)
                self.assertEqual(self.window.tab_paths.guest_ssh_enable.text(),'Local SSH enabled')
        finally:release.set();timer.stop()

    def test_add_gpu_assigns_captured_rom_only_to_graphics(self):
        tab=self.window.tab_hw
        tab.host_gpus=[dict(slot='0000:01:00.0',functions=[dict(slot='0000:01:00.0'),dict(slot='0000:01:00.1')])]
        tab.gpu_combo.clear();tab.gpu_combo.addItem('Fixture GPU','0000:01:00.0')
        captured=[]
        def capture(slot,done):
            captured.append(slot);done('/fixture/validated.rom')
        tab.capture_gpu_rom=capture;tab._add_gpu()
        devices={d['host']:d for d in self.window.cfg.devices if d.get('driver')=='vfio-pci'}
        self.assertEqual(captured,['0000:01:00.0'])
        self.assertEqual(devices['0000:01:00.0']['romfile'],'/fixture/validated.rom')
        self.assertNotIn('romfile',devices['0000:01:00.1'])

    def gpu_wizard_fixture(self):
        import hostinfo
        wizard=self.window.tab_wizard
        gpus=[dict(slot=slot,device='Fixture GPU',functions=[dict(slot=slot),dict(slot=slot[:-1]+'1')])
              for slot in ('0000:01:00.0','0000:02:00.0')]
        self.window.cfg.devices.extend([
            dict(driver='vfio-pci',host='0000:01:00.0',id='fixture-gpu',romfile='/old-machine/gpu.rom'),
            dict(driver='vfio-pci',host='0000:01:00.1',id='fixture-audio'),
        ])
        for mock in (patch.object(hostinfo,'gpus',return_value=gpus),
                     patch.object(hostinfo,'pci_devices',return_value=[]),
                     patch.object(wizard,'_baseline_pci_matches',return_value=True)):
            mock.start();self.addCleanup(mock.stop)
        wizard.go(5)
        return wizard

    def test_wizard_rom_starts_empty_and_browse_choice_stays_with_its_gpu(self):
        from PyQt6.QtWidgets import QFileDialog
        wizard=self.gpu_wizard_fixture()
        self.assertEqual(wizard.gpu_combo.currentData(),'0000:01:00.0')
        self.assertEqual(wizard.gpu_rom.text(),'')
        self.assertTrue(wizard.gpu_autodump.isEnabled())
        devices=copy.deepcopy(self.window.cfg.devices)
        with patch.object(QFileDialog,'getOpenFileName',return_value=('/chosen/gpu.rom','')):
            wizard.gpu_browse.click()
        wizard.gpu_combo.setCurrentIndex(2)
        self.assertEqual(wizard.gpu_rom.text(),'')
        wizard.gpu_combo.setCurrentIndex(1)
        self.assertEqual(wizard.gpu_rom.text(),'/chosen/gpu.rom')
        wizard.go(6);wizard.go(5)
        self.assertEqual(wizard.gpu_rom.text(),'/chosen/gpu.rom')
        wizard.gpu_combo.setCurrentIndex(0)
        self.assertFalse(wizard.gpu_autodump.isEnabled())
        self.assertEqual(self.window.cfg.devices,devices)

    def test_wizard_autodump_uses_shared_worker_and_applies_only_on_next(self):
        import gpu_rom
        from PyQt6.QtWidgets import QMessageBox
        wizard=self.gpu_wizard_fixture();before=copy.deepcopy(self.window.cfg.devices)
        with patch.object(gpu_rom,'capture',return_value='/fixture/prepared.rom') as capture, \
             patch.object(self.window,'_busy',return_value=False),patch.object(QMessageBox,'information'):
            wizard.gpu_autodump.click();self.wait_for_operation()
        capture.assert_called_once_with('0000:01:00.0')
        self.assertEqual(wizard.gpu_rom.text(),'/fixture/prepared.rom')
        self.assertIn('automatically dumped',wizard.gpu_rom_status.text())
        self.assertTrue(wizard.btn_next.isEnabled())
        self.assertEqual(self.window.cfg.devices,before)
        wizard.next_action()
        devices={d['host']:d for d in self.window.cfg.devices if d.get('driver')=='vfio-pci' and not d.get('_disabled')}
        self.assertEqual(devices['0000:01:00.0']['romfile'],'/fixture/prepared.rom')
        self.assertNotIn('romfile',devices['0000:01:00.1'])

    def test_wizard_autodump_failure_restores_controls_and_preserves_path(self):
        import gpu_rom
        from PyQt6.QtWidgets import QMessageBox
        wizard=self.gpu_wizard_fixture();wizard.gpu_rom.setText('/chosen/working.rom')
        with patch.object(gpu_rom,'capture',side_effect=RuntimeError('ROM unavailable. Use Browse.')), \
             patch.object(self.window,'_busy',return_value=False),patch.object(QMessageBox,'warning') as warning:
            wizard.gpu_autodump.click();self.wait_for_operation()
        warning.assert_called_once()
        self.assertEqual(wizard.gpu_rom.text(),'/chosen/working.rom')
        self.assertTrue(wizard.gpu_autodump.isEnabled())
        self.assertTrue(wizard.btn_next.isEnabled())
        self.assertIn('Retry or Browse',wizard.gpu_rom_status.text())

    def test_wizard_empty_rom_does_not_dump_implicitly_on_next(self):
        wizard=self.gpu_wizard_fixture()
        with patch.object(wizard,'capture_gpu_rom',side_effect=AssertionError('Next unexpectedly dumped the GPU')):
            self.assertTrue(wizard.next_action())
        devices=[d for d in self.window.cfg.devices if d.get('driver')=='vfio-pci' and not d.get('_disabled')]
        self.assertTrue(devices)
        self.assertFalse(any(d.get('romfile') for d in devices))

    def test_wizard_dump_cannot_advance_or_update_a_rebuilt_step(self):
        wizard=self.gpu_wizard_fixture();callbacks=[]
        with patch.object(wizard,'capture_gpu_rom',side_effect=lambda slot,done:callbacks.append(done)):
            wizard.gpu_autodump.click()
        self.assertFalse(wizard.btn_next.isEnabled())
        self.assertFalse(wizard.gpu_combo.isEnabled())
        self.assertFalse(wizard.next_action())
        wizard.go(6);wizard.go(5)
        self.application.sendPostedEvents(None,self.kvm.QEvent.Type.DeferredDelete)
        callbacks[0]('/stale/another-gpu.rom')
        self.assertEqual(wizard.gpu_rom.text(),'')
        self.assertTrue(wizard.btn_next.isEnabled())

    def test_missing_tpm_highlights_page_and_offers_setup(self):
        import health
        health.refresh(self.window)
        self.assertTrue(self.window.navigation.items['TPM'].data(health.ISSUE_ROLE))
        self.assertFalse(self.window.tab_tpm.btn_repair.isHidden())
        self.assertTrue(self.window.issue_delegate.timer.isActive())
        self.window.tab_tpm.last_checks=[('PASS','TPM','Ready')]
        health.refresh(self.window)
        self.assertFalse(self.window.navigation.items['TPM'].data(health.ISSUE_ROLE))

    def test_compatible_module_prepares_and_clears_warning_before_launch(self):
        import editions,health,module_policy,packages,platform
        w=self.window;panel=w.package_panel
        editions.select('xetallic');w.cfg.data['tools']['kvm_build_enabled']=True
        panel.store=packages.Store(edition='xetallic');panel.load_catalog()
        entry=copy.deepcopy(panel.release['components']['kvm-amd'])
        entry['kernel']=platform.release();entry.pop('runtime',None)
        panel.release['components']['kvm-amd']=entry
        def download(name,selected,progress):
            self.assertEqual(name,'kvm-amd')
            directory=panel.store.root/'components/kvm-amd/current';directory.mkdir(parents=True,exist_ok=True)
            packages.atomic_json(directory/'.component.json',selected)
            for filename in ('load-kvm.sh','kvm.ko','kvm-amd.ko'):
                (directory/filename).write_text('fixture; never execute')
        with patch.object(module_policy,'requested',return_value=True), \
             patch.object(module_policy,'busy_reason',return_value=''), \
             patch.object(packages,'cpu_vendor',return_value='amd'), \
             patch.object(w,'_busy',return_value=False), \
             patch.object(panel.store,'download',side_effect=download) as downloaded, \
             patch('module_tool.check',side_effect=AssertionError('Settings must not load modules')):
            health.refresh(w)
            self.assertTrue(all('compatible' in warning.text() for warning in w.module_warnings))
            self.application.processEvents();self.wait_for_operation();self.application.processEvents()
            downloaded.assert_called_once()
            self.assertTrue(all(warning.isHidden() for warning in w.module_warnings))
            self.assertEqual(module_policy.unavailable(),'')
        import shutil
        shutil.rmtree(panel.store.root/'components/kvm-amd')

    def test_tpm_selection_and_health_survive_close_and_new_window(self):
        import tpm_actions,tpm_setup
        tab=self.window.tab_tpm
        state=portable.data_root()/'tpm-identities/saved-fixture/state';state.mkdir(parents=True,exist_ok=True)
        blob=state/'tpm2-00.permall';blob.write_bytes(b'saved guest keys');blob.chmod(0o600)
        choice={**tpm_actions.snapshot(tab),'binary':sys.executable,'state':str(state),
                'values':copy.deepcopy(next(iter(__import__('tabs_tpm').PRESETS.values()))),'label':'Saved fixture TPM'}
        actual={number:int(choice['values'][key],0) for key,number in tpm_actions.PROPERTIES.items()}
        def inspect(binary,data,stamp,identity=False):return actual if identity else (('sha1','sha256'),True)
        with patch.object(tpm_actions,'prepare',return_value=choice), \
             patch.object(tpm_setup,'inspect_state',side_effect=inspect), \
             patch.object(self.window,'_busy',return_value=False):
            self.window._tpm_action('bundled');self.wait_for_operation()
            self.window.close()
            reopened=self.kvm.KVMSettings()
            try:
                self.assertEqual(reopened.cfg.data['tools']['swtpm_state'],str(state))
                self.assertEqual(reopened.cfg.data['tpm_choice'],'Saved fixture TPM')
                self.assertFalse([c for c in reopened.tab_tpm.last_checks if c[0]=='FAIL'])
                self.assertEqual(blob.read_bytes(),b'saved guest keys')
            finally:
                reopened.hide();reopened.deleteLater()

    def test_component_check_pulses_paths_and_clears_after_updates(self):
        import health
        import packages
        w=self.window;panel=w.package_panel;item=w.navigation.items['Paths && Tools']
        installed=copy.deepcopy(panel.release['components'])
        release=copy.deepcopy(panel.release)
        for name in ('qemu','ovmf'):
            release['components'][name].update(version='2.0.0',sha256='b'*64)
        # Isolate update notices from the missing files in this test workspace.
        w.cfg.data['_meta']['binary']=sys.executable
        w.cfg.data['tools']['kvm_build_enabled']=False
        with patch.object(w.cfg,'validate',return_value=[]), \
             patch.object(packages,'installed',side_effect=lambda name,root=None:installed.get(name,{})), \
             patch.object(panel.store,'check',return_value=release), \
             patch.object(panel.store,'download') as download, \
             patch.object(portable,'prepare_firmware') as firmware, \
             patch.object(portable,'prepare_tpm_workspace') as tpm:
            panel.refresh()
            self.assertFalse(item.data(health.ISSUE_ROLE))
            panel.check_updates();self.wait_for_operation()
            self.assertTrue(item.data(health.ISSUE_ROLE))
            self.assertTrue(w.issue_delegate.timer.isActive())
            for name in ('qemu','ovmf'):
                expected=f'{installed[name]["label"]} update available: {installed[name]["version"]} → 2.0.0.'
                self.assertIn(expected,item.toolTip())
                row=next(r for r in range(panel.table.rowCount()) if panel.table.item(r,0).text()==release['components'][name]['label'])
                self.assertEqual(panel.table.item(row,3).text(),'UPDATE AVAILABLE')
            w._select_tab_by_name('Paths & Tools')
            self.assertIn('update available',w.issue_banner.text())
            # A failed later check must not discard previously verified updates.
            with patch.object(panel.store,'check',side_effect=RuntimeError('Offline fixture')):
                panel.check_updates();self.wait_for_operation()
            self.assertTrue(item.data(health.ISSUE_ROLE))
            self.assertIn('Offline fixture',panel.info.text())
            # Installing one component clears only its own notice.
            installed['qemu']=copy.deepcopy(release['components']['qemu'])
            panel.refresh()
            self.assertTrue(item.data(health.ISSUE_ROLE))
            self.assertNotIn(installed['qemu']['label']+' update available',item.toolTip())
            self.assertIn(installed['ovmf']['label']+' update available',item.toolTip())
            # An external component update also clears on the next health tick.
            installed['ovmf']=copy.deepcopy(release['components']['ovmf'])
            health.refresh(w)
            self.assertFalse(item.data(health.ISSUE_ROLE))
            self.assertEqual(item.toolTip(),w.issue_tooltips['Paths && Tools'])
            self.assertTrue(w.issue_banner.isHidden())
            self.assertTrue(w.navigation.items['TPM'].data(health.ISSUE_ROLE))
            download.assert_not_called();firmware.assert_not_called();tpm.assert_not_called()

    def test_component_version_conflict_is_not_an_update(self):
        import packages
        from PyQt6.QtWidgets import QPushButton
        panel=self.window.package_panel
        installed=copy.deepcopy(panel.release['components'])
        panel.release=copy.deepcopy(panel.release)
        panel.release['components']['qemu']['sha256']='b'*64
        with patch.object(packages,'installed',side_effect=lambda name,root=None:installed.get(name,{})):
            panel.refresh()
            self.assertEqual(panel.update_messages(),[])
            row=next(r for r in range(panel.table.rowCount()) if panel.table.item(r,0).text()==panel.release['components']['qemu']['label'])
            self.assertEqual(panel.table.item(row,3).text(),'Version conflict')
            self.assertFalse(panel.table.cellWidget(row,4).findChild(QPushButton).isEnabled())

    def wait_for_operation(self):
        deadline=time.monotonic()+5
        while self.window.package_panel.job and time.monotonic()<deadline:
            self.application.processEvents();time.sleep(.01)
        self.assertIsNone(self.window.package_panel.job)

    def test_tpm_choice_applies_saves_and_undoes_without_questions(self):
        import tpm_actions
        from PyQt6.QtWidgets import QMessageBox
        tab=self.window.tab_tpm;before=tpm_actions.snapshot(tab)
        choice={**copy.deepcopy(before),'binary':'/fixture/new/swtpm','state':'/fixture/new/state','label':'Fixture identity'}
        with patch.object(tpm_actions,'prepare',return_value=choice),patch.object(self.window,'_busy',return_value=False),patch.object(QMessageBox,'question',side_effect=AssertionError('One-click choice asked a question')):
            self.window._tpm_action('bundled');self.wait_for_operation()
            self.assertEqual(self.window.cfg.data['tools']['swtpm_binary'],choice['binary'])
            saved=json.loads(self.window._paths().session.read_text())
            self.assertEqual(saved['tpm_previous'],before)
            self.assertEqual(saved['tpm_choice'],'Fixture identity')
            self.window._tpm_action('undo');self.wait_for_operation()
        self.assertEqual(tpm_actions.snapshot(tab),before)
        self.assertNotIn('tpm_previous',self.window.cfg.data)

    def test_tpm_choice_failure_leaves_selection_unchanged(self):
        import tpm_actions
        before=tpm_actions.snapshot(self.window.tab_tpm)
        with patch.object(tpm_actions,'prepare',side_effect=RuntimeError('fixture build failed')),patch.object(self.window,'_busy',return_value=False):
            self.window._tpm_action('random');self.wait_for_operation()
        self.assertEqual(tpm_actions.snapshot(self.window.tab_tpm),before)
        self.assertIn('Not applied',self.window.tab_tpm.action_status.text())
        self.assertNotIn('tpm_previous',self.window.cfg.data)

    def test_tpm_choices_keep_technical_fields_collapsed(self):
        tab=self.window.tab_tpm
        self.window.resize(1820,920);self.window._select_tab_by_name('TPM');self.application.processEvents()
        self.assertTrue(tab.advanced.isHidden());self.assertEqual(len(tab.quick_buttons),8)
        self.assertTrue(tab.quick_buttons['bundled'].isEnabled())
        self.assertFalse(tab.quick_buttons['random'].isEnabled())  # No private builder in a fresh fixture.
        tab.advanced_toggle.click();self.assertFalse(tab.advanced.isHidden())

    def test_cpu_choices_fit_every_palette_and_layout(self):
        from PyQt6.QtWidgets import QStyle,QStyleOptionComboBox
        theme=self.kvm.desktop_theme
        self.window.resize(1820,920);self.window._select_tab_by_name('CPU Features')
        for design in ('raw','modern','breakpoint','binaryknife'):
            for mode in ('dark','light'):
                for layout in ('classic','modern','sidebar','ribbon'):
                    with self.subTest(design=design,mode=mode,layout=layout),patch.object(theme,'state',return_value=dict(design=design,mode=mode,layout=layout)):
                        self.application.hypr_theme.apply();self.application.processEvents()
                        for table in (self.window.feat_amd,self.window.feat_intel,self.window.feat_uni):
                            for row in range(table.rowCount()):
                                combo=table.cellWidget(row,1)
                                option=QStyleOptionComboBox();combo.initStyleOption(option)
                                rect=combo.style().subControlRect(QStyle.ComplexControl.CC_ComboBox,option,QStyle.SubControl.SC_ComboBoxEditField,combo)
                                width=max(combo.fontMetrics().horizontalAdvance(combo.itemText(i)) for i in range(combo.count()))
                                self.assertGreaterEqual(rect.width(),width)
                                self.assertGreaterEqual(rect.height(),combo.fontMetrics().height())
        self.application.hypr_theme.apply()

    def test_smbios_regenerate_buttons_fit_themes_and_change_only_their_field(self):
        from PyQt6.QtWidgets import QPushButton,QStyle,QStyleOptionButton
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        theme=self.kvm.desktop_theme;w=self.window
        w.resize(1820,920);w._select_tab_by_name('SMBIOS')
        for design in ('raw','modern','breakpoint','binaryknife'):
            for mode in ('dark','light'):
                with self.subTest(design=design,mode=mode),patch.object(theme,'state',return_value=dict(design=design,mode=mode,layout='sidebar')):
                    self.application.hypr_theme.apply();self.application.processEvents()
                    table=w.smbios_table
                    w.tab_smbios.ensureWidgetVisible(table)
                    self.application.processEvents()
                    for row in range(table.rowCount()):
                        button=table.cellWidget(row,4).findChild(QPushButton)
                        option=QStyleOptionButton();button.initStyleOption(option)
                        rect=button.style().subElementRect(QStyle.SubElement.SE_PushButtonContents,option,button)
                        self.assertGreaterEqual(rect.width(),button.fontMetrics().horizontalAdvance('Regenerate'))
                        self.assertGreaterEqual(rect.height(),button.fontMetrics().height())
                    before=copy.deepcopy(w.cfg.smbios['patches']);row=min(2,len(before)-1)
                    table.scrollToItem(table.item(row,1));self.application.processEvents()
                    button=table.cellWidget(row,4).findChild(QPushButton)
                    replacement='Z'*len(before[row]['find_ascii'])
                    with patch.object(self.kvm.vmstart2.randomize,'like',return_value=replacement):
                        QTest.mouseClick(button,Qt.MouseButton.LeftButton)
                    after=w.cfg.smbios['patches']
                    self.assertEqual(after[row]['replace_ascii'],replacement)
                    self.assertEqual(after[row]['replace_hex'],replacement.encode().hex())
                    self.assertEqual(after[:row]+after[row+1:],before[:row]+before[row+1:])
                    self.assertEqual(after[row]['find_ascii'],before[row]['find_ascii'])
        self.application.hypr_theme.apply()


if __name__=='__main__':unittest.main()
