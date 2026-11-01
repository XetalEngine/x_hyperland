"""Build option enforcement before installation; no mounts or disk commands."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]/'iso'
spec=importlib.util.spec_from_file_location('account_selection',ROOT/'installer_account.py')
account=importlib.util.module_from_spec(spec);spec.loader.exec_module(account)


class AccountSelectionTests(unittest.TestCase):
    def select(self,enabled,plan,status=0):
        with tempfile.TemporaryDirectory(prefix='iso-account-selection-') as tmp:
            root=Path(tmp);clone=root/'clone';clone.mkdir()
            shutil.copy2(ROOT/'installer_account.py',clone)
            (clone/'firstboot.conf').write_text('CHANGE_USER='+str(int(enabled))+'\n')
            script=root/'installer.sh';script.write_text((ROOT/'installer.sh').read_text().replace('/opt/clone',str(clone)))
            (root/'choice').write_text(json.dumps(plan))
            code='''
source "$1"
fixture=$2
fixture_status=$3
installer_ui() { echo called >> "$fixture/calls"; cat "$fixture/choice"; return "$fixture_status"; }
installer_account_choice
result=$?
printf '%s\\n' "$ACCOUNT_PLAN" "$ACCOUNT_SUMMARY"
exit "$result"
'''
            result=subprocess.run(['bash','-c',code,'test',str(script),str(root),str(status)],capture_output=True,text=True,timeout=5)
            return result,(root/'calls').exists()

    def test_disabled_option_skips_page_and_preserves_source_account(self):
        result,called=self.select(False,{'change':True})
        self.assertEqual(result.returncode,0,result.stderr);self.assertFalse(called)
        self.assertIn('{"change":false}',result.stdout)
        self.assertIn('Keep existing accounts and passwords.',result.stdout)

    def test_enabled_option_cannot_keep_old_account_or_skip_password(self):
        users=[dict(name='alice',uid=1000,gid=1000,home='/home/alice')]
        valid=account.choice(users,0,'airton','x','x')
        for plan in ({'change':False},valid|{'password_hash':''},valid|{'username':'alice'}):
            with self.subTest(plan=plan):
                result,called=self.select(True,plan)
                self.assertNotEqual(result.returncode,0);self.assertTrue(called)

    def test_enabled_option_accepts_fresh_account_with_simple_password(self):
        plan=account.choice([dict(name='alice',uid=1000,gid=1000,home='/home/alice')],0,'airton','phphph','phphph')
        result,called=self.select(True,plan)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(called)
        self.assertIn('New administrator: airton',result.stdout)
        self.assertNotIn('phphph',result.stdout+result.stderr)

    def test_back_cancels_account_selection(self):
        result,called=self.select(True,{},10)
        self.assertEqual(result.returncode,10);self.assertTrue(called)


if __name__=='__main__':unittest.main()
