"""Exercise UI entry points and session ownership with private local sockets."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parent


class SessionCacheTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='ui-cache-')
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.instance = self.root / 'hypr/fixture'
        self.instance.mkdir(parents=True)
        self.env = dict(os.environ, XDG_RUNTIME_DIR=str(self.root),
                        HYPRLAND_INSTANCE_SIGNATURE='fixture')

    def server(self, name):
        server = socket.socket(socket.AF_UNIX)
        self.addCleanup(server.close)
        server.bind(str(self.instance / name))
        server.listen(8)
        server.settimeout(5)
        return server

    def test_theme_and_settings_share_endpoint_and_preserve_arguments(self):
        settings = self.server('control-center.sock')
        panel = self.server('.xpanel.sock')
        cases = [
            (['theme', '/tmp/a wallpaper.png'], settings,
             {'tab': 'theme', 'wallpaper': '/tmp/a wallpaper.png', 'preload': False}),
            (['settings', '--window-hints'], settings,
             {'tab': 'window-hints', 'wallpaper': '', 'preload': False}),
            (['settings', '--preload'], settings,
             {'tab': 'hotkeys', 'wallpaper': '', 'preload': True}),
            (['panel', '--section', 'cleaner'], panel,
             {'section': 'cleaner', 'preload': False}),
            (['panel', '--section', 'deb', '--deb-file', "/tmp/package's $(literal).deb"], panel,
             {'section': 'deb', 'preload': False, 'deb_file': "/tmp/package's $(literal).deb"}),
        ]
        for arguments, server, expected in cases:
            with self.subTest(arguments=arguments):
                result = subprocess.run([sys.executable, str(SOURCE / 'client.py'), *arguments],
                                        env=self.env, capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                peer, _ = server.accept()
                with peer:
                    peer.settimeout(2)
                    with peer.makefile('rb') as stream:
                        self.assertEqual(json.loads(stream.readline()), expected)

    def test_owner_recovers_exited_ui_and_stops_only_owned_children_on_logout(self):
        compositor = self.server('.socket2.sock')
        existing_panel = self.server('.xpanel.sock')
        scripts = self.root / 'scripts'
        scripts.mkdir()
        worker = self.root / 'worker.py'
        worker.write_text('''import os, signal, socket, sys, time
from pathlib import Path
root=Path(__file__).parent
name, endpoint=sys.argv[1:3]
path=root/'hypr/fixture'/endpoint
path.unlink(missing_ok=True)
server=socket.socket(socket.AF_UNIX);server.bind(str(path));server.listen(4)
def stop(*_):
    (root/(str(os.getpid())+'.stopped')).write_text('stopped')
    sys.exit(0)
signal.signal(signal.SIGTERM,stop)
(root/(name+'.pid')).write_text(str(os.getpid()))
while True: time.sleep(.1)
''')
        for script, name, endpoint in [('launcher.sh', 'apps', 'xetal-launcher.sock'),
                                       ('control-center.sh', 'settings', 'control-center.sock'),
                                       ('control-panel.sh', 'panel', '.xpanel.sock')]:
            path = scripts / script
            path.write_text('#!' + sys.executable + '\nimport os\nos.execv(' +
                            repr(sys.executable) + ',' +
                            repr([sys.executable, str(worker), name, endpoint]) + ')\n')
            path.chmod(0o700)
        code = 'import preload;from pathlib import Path;preload.ROOT=Path(' + repr(str(self.root)) + ');raise SystemExit(preload.main())'
        owner = subprocess.Popen([sys.executable, '-c', code], cwd=SOURCE, env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            if owner.poll() is None: owner.terminate()
            try: owner.communicate(timeout=5)
            except subprocess.TimeoutExpired: owner.kill(); owner.communicate()
        self.addCleanup(cleanup)
        lifetime, _ = compositor.accept()
        self.addCleanup(lifetime.close)

        def wait_pid(name, previous=None):
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                try:
                    pid = int((self.root / (name + '.pid')).read_text())
                    if pid != previous: return pid
                except (OSError, ValueError): pass
                time.sleep(.02)
            self.fail(name + ' was not preloaded/recovered')

        apps = wait_pid('apps')
        settings = wait_pid('settings')
        self.assertFalse((self.root / 'panel.pid').exists(), 'Existing panel was duplicated')
        os.kill(apps, signal.SIGTERM)
        recovered_apps = wait_pid('apps', apps)
        lifetime.close()
        stdout, stderr = owner.communicate(timeout=5)
        self.assertEqual(owner.returncode, 0, stderr)
        for pid in (apps, recovered_apps, settings):
            self.assertTrue((self.root / (str(pid) + '.stopped')).exists(), 'Owned UI survived logout')
        self.assertFalse((self.root / 'panel.pid').exists())
        self.assertGreaterEqual(existing_panel.fileno(), 0, 'Unowned endpoint was closed')


if __name__ == '__main__': unittest.main()
