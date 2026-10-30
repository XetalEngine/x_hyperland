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
from unittest.mock import patch

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

    def test_missing_tpm_highlights_page_and_offers_setup(self):
        import health
        health.refresh(self.window)
        self.assertTrue(self.window.navigation.items['TPM'].data(health.ISSUE_ROLE))
        self.assertFalse(self.window.tab_tpm.btn_repair.isHidden())
        self.assertTrue(self.window.issue_delegate.timer.isActive())
        self.window.tab_tpm.last_checks=[('PASS','TPM','Ready')]
        health.refresh(self.window)
        self.assertFalse(self.window.navigation.items['TPM'].data(health.ISSUE_ROLE))

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


if __name__=='__main__':unittest.main()
