"""Update guards use process identity, not the existence of a previous log."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from activity import supervisor_active


class ActivityTests(unittest.TestCase):
    def test_completed_missing_reused_and_live_supervisors(self):
        with tempfile.TemporaryDirectory() as directory:
            proc=Path(directory);(proc/'42').mkdir()
            stat=proc/'42/stat'
            stat.write_text('42 (VM supervisor) '+' '.join(['S']+['0']*18+['123']))
            state=dict(state='running',pid=42,process_start='123')
            self.assertTrue(supervisor_active(state,proc))
            self.assertFalse(supervisor_active(dict(state,state='stopped'),proc))
            self.assertFalse(supervisor_active(dict(state,process_start='124'),proc))
            stat.write_text(stat.read_text().replace(') S ',') Z '))
            self.assertFalse(supervisor_active(state,proc))
            stat.unlink()
            self.assertFalse(supervisor_active(state,proc))

    def test_unreadable_supervisor_blocks_updates(self):
        with patch.object(Path,'read_text',side_effect=PermissionError):
            self.assertTrue(supervisor_active(dict(state='running',pid=42,process_start='123')))

    def test_opening_panel_does_not_update_a_running_guest(self):
        from package_ui import PackagesPanel
        panel=SimpleNamespace(busy=lambda:True,check_updates=Mock())
        with patch('portable.prepare_firmware') as firmware, \
             patch('portable.prepare_tpm_workspace') as tpm:
            PackagesPanel.bootstrap(panel)
        firmware.assert_not_called();tpm.assert_not_called()
        panel.check_updates.assert_called_once_with()


if __name__=='__main__':unittest.main()
