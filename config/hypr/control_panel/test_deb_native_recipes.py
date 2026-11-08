"""Native integration regressions from vendor layouts reviewed 2026-11-08."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import deb_recipes as recipes


class NativeRecipeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.write('.PKGINFO', 'pkgname = converted-app\npkgver = 1.0\n')
        # Valid-looking translated scripts must be replaced too, never run.
        self.write('.INSTALL', 'post_install() { touch /should-not-run; }\n')

    def write(self, name, text='fixture', executable=False):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'\x7fELFfixture' if executable else text.encode())
        path.chmod(0o755 if executable else 0o644)
        return path

    def opera(self):
        for name in ('opera', 'opera_sandbox'):
            self.write('usr/lib/x86_64-linux-gnu/opera-stable/'+name, executable=True)
        self.write('usr/share/applications/opera.desktop', '[Desktop Entry]\nName=Opera\nExec=opera %U\n')

    def onepassword(self):
        for name in ('1password', '1Password-BrowserSupport', '1password-mcp', 'chrome-sandbox'):
            self.write('opt/1Password/'+name, executable=True)
        self.write('usr/share/applications/com.onepassword.OnePassword.desktop')
        self.write('opt/1Password/resources/custom_allowed_browsers', 'vendor browser defaults\n')
        policy = '<policyconfig><action id="com.1password.1Password.unlock"/>'
        for name in ('authorizeCLI', 'authorizeSshAgent'):
            policy += '<action id="com.1password.1Password.'+name+'"><annotate key="org.freedesktop.policykit.owner">${POLICY_OWNERS}</annotate></action>'
        self.write('opt/1Password/com.1password.1Password.policy.tpl', policy+'</policyconfig>')

    def anydesk(self):
        self.write('usr/bin/anydesk', executable=True)
        self.write('usr/share/applications/anydesk.desktop')
        self.write('usr/share/polkit-1/actions/com.anydesk.anydesk.policy')
        self.write('usr/share/anydesk/files/systemd/anydesk.service', '[Service]\nExecStart=/usr/bin/anydesk --service\nUser=root\n')

    def test_opera_replaces_only_recognized_setup_dependencies(self):
        fields = {'package':recipes.OPERA, 'pre-depends':'apt-transport-https',
                  'depends':'debconf (>= 0.5) | debconf-2.0, libqt5core5a (>= 5.3.0)'}
        adapted = recipes.dependency_fields(fields)
        self.assertNotIn('pre-depends', adapted)
        self.assertNotIn('debconf', adapted['depends'])
        self.assertIn('libqt5core5a (>= 5.3.0)', adapted['depends'])
        for value in ('apt-transport-https | new-runtime', 'apt-transport-https:arm64', 'apt-transport-https (<< 2)'):
            self.assertEqual(recipes.dependency_fields(dict(fields, **{'pre-depends':value}))['pre-depends'], value)
        self.assertEqual(recipes.dependency_fields(dict(fields, package='other')), dict(fields, package='other'))

    def test_opera_keeps_vendor_launcher_and_packages_sandbox_mode(self):
        self.opera()
        recipes.finalize(self.root, recipes.OPERA)
        self.assertEqual((self.root/'usr/bin/opera').resolve(), self.root/'usr/lib/x86_64-linux-gnu/opera-stable/opera')
        self.assertEqual((self.root/'usr/lib/x86_64-linux-gnu/opera-stable/opera_sandbox').stat().st_mode & 0o7777, 0o4755)
        self.assertIn('conflict = opera\n', (self.root/'.PKGINFO').read_text())
        self.assertNotIn('touch', (self.root/'.INSTALL').read_text())
        recipes.finalize(self.root, recipes.OPERA)

    def test_anydesk_service_is_owned_and_enablement_stays_a_user_choice(self):
        self.anydesk()
        adapted = recipes.dependency_fields({'package':recipes.ANYDESK, 'depends':'libgcc1 (>= 1:4.1.1)'})
        self.assertIn('libevdev', adapted['depends'].split(', '))
        self.assertIn('libgcc1 (>= 1:4.1.1)', adapted['depends'])
        recipes.finalize(self.root, recipes.ANYDESK)
        self.assertEqual((self.root/'usr/lib/systemd/system/anydesk.service').read_bytes(), (self.root/'usr/share/anydesk/files/systemd/anydesk.service').read_bytes())
        script = (self.root/'.INSTALL').read_text()
        self.assertNotIn('touch', script)
        self.assertNotIn('deb-systemd', script)
        self.assertFalse((self.root/'etc/systemd').exists())
        # Executing post_install only prints the opt-in instruction.
        result = subprocess.run(['bash', '-c', script+'\npost_install'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('optional', result.stdout)
        self.assertIn('conflict = anydesk-bin\n', (self.root/'.PKGINFO').read_text())

    def test_onepassword_owned_integration_and_config_backup(self):
        self.onepassword()
        recipes.finalize(self.root, recipes.ONEPASSWORD)
        self.assertEqual((self.root/'usr/bin/1password').readlink(), Path('/opt/1Password/1password'))
        self.assertEqual((self.root/'usr/bin/1password-mcp').readlink(), Path('/opt/1Password/1password-mcp'))
        self.assertIn('backup = etc/1password/custom_allowed_browsers\n', (self.root/'.PKGINFO').read_text())
        helper = (self.root/'usr/lib/hyperfusion-deb/1password-setup.py').read_text()
        compile(helper, '1password-setup.py', 'exec')
        self.assertIn('post_upgrade() { post_install; }', (self.root/'.INSTALL').read_text())
        self.assertFalse((self.root/'etc/apt').exists())
        self.assertEqual((self.root/'opt/1Password/chrome-sandbox').stat().st_mode & 0o7777, 0o4755)
        recipes.finalize(self.root, recipes.ONEPASSWORD)

    def test_changed_layouts_and_symlinked_destinations_stop_before_install(self):
        self.opera()
        outside = self.root/'outside'; outside.mkdir()
        (self.root/'usr/bin').symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, 'unexpected symbolic link'):
            recipes.finalize(self.root, recipes.OPERA)
        self.assertEqual(list(outside.iterdir()), [])
        (self.root/'usr/bin').unlink()
        self.onepassword()
        self.write('opt/1Password/com.1password.1Password.policy.tpl', '<broken>${POLICY_OWNERS}${POLICY_OWNERS}')
        with self.assertRaisesRegex(RuntimeError, 'policy template is invalid'):
            recipes.finalize(self.root, recipes.ONEPASSWORD)

    @unittest.skipUnless(shutil.which('fakeroot'), 'fakeroot required for root-owned fixture')
    def test_native_onepassword_setup_and_postcheck_use_target_users_and_protected_groups(self):
        self.onepassword()
        recipes.finalize(self.root, recipes.ONEPASSWORD)
        # Exercise the actual generated helper twice in a disposable tree.
        # fakeroot contains ownership changes; no host users/groups are touched.
        helper = recipes.ONEPASSWORD_SETUP.replace("'/opt/", repr(str(self.root)) + "+'/opt/").replace("'/usr/", repr(str(self.root)) + "+'/usr/")
        setup = self.write('setup.py', helper)
        wrapper = self.write('check.py', '''import grp, os, pwd, runpy, subprocess, sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[2])
import deb_recipes
root = Path(sys.argv[1])
subprocess.run(['chown', '-hR', '0:0', str(root)], check=True)
grp.getgrnam = lambda name: SimpleNamespace(gr_gid=1234 if name == 'onepassword' else 1235)
pwd.getpwall = lambda: [SimpleNamespace(pw_name='root', pw_uid=0), SimpleNamespace(pw_name='guest', pw_uid=1000)]
for _ in range(2):
    runpy.run_path(str(root/'setup.py'))
    deb_recipes.verify_installed_recipe('1password', root)
policy = root/'usr/share/polkit-1/actions/com.1password.1Password.policy'
assert policy.read_text().count('unix-user:guest') == 2
policy.write_text(policy.read_text().replace('unix-user:guest', 'unix-user:root'))
try:
    deb_recipes.verify_installed_recipe('1password', root)
except RuntimeError as error:
    assert 'did not finish' in str(error)
else:
    raise AssertionError('Incomplete native policy setup was accepted')
''')
        result = subprocess.run(['fakeroot', 'python', str(wrapper), str(self.root), str(Path(recipes.__file__).parent)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
