"""Real child processes and a disposable session socket; never the live desktop."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import github
import service
import update_engine as engine


class LifecycleTests(unittest.TestCase):
    def test_unpublished_developer_revision_does_not_offer_an_old_remote_release(self):
        with tempfile.TemporaryDirectory(prefix='xetal-unpublished-test-') as directory:
            root=Path(directory);origin=root/'origin';origin.mkdir()
            def git(repo,*args):
                return subprocess.check_output(['git','-C',str(repo),'-c','user.name=Fixture',
                    '-c','user.email=fixture@example.invalid',*args],text=True,stderr=subprocess.PIPE).strip()
            git(origin,'init','-q','-b','main');(origin/'code').write_text('published')
            git(origin,'add','.');git(origin,'commit','-qm','Published')
            published=git(origin,'rev-parse','HEAD')
            clone=root/'developer';git(origin,'clone','-q',str(origin),str(clone))
            (clone/'code').write_text('new local work');git(clone,'commit','-qam','Unpublished')
            current=git(clone,'rev-parse','HEAD')
            with patch.object(github,'REPOSITORY',str(origin)):
                value=github.git_latest(current,cache=root/'cache')
            self.assertEqual(value['sha'],published);self.assertEqual(value['relation'],'unknown')
            live=root/'profile';live.mkdir()
            engine.write_json(live/engine.META,engine.metadata(live,current))
            with patch.object(github,'latest',return_value=value):status=service.check(live,root/'state')
            self.assertEqual(service.badge(status)['text'],'')

    def test_logout_stops_network_worker_and_detached_descendant(self):
        with tempfile.TemporaryDirectory(prefix='xetal-session-test-') as directory:
            root = Path(directory); runtime = root/'hypr/fixture'; runtime.mkdir(parents=True)
            wrapper = root/'worker.py'; state = root/'state'
            wrapper.write_text('''import json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0, '''+repr(str(Path(service.__file__).parent))+''')
import service
root=Path('''+repr(str(root))+''')
if '--check' in sys.argv:
 p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'],start_new_session=True)
 (root/'pids.json').write_text(json.dumps([os.getpid(),p.pid]))
 time.sleep(120)
else:
 service.STATE=root/'state';service.__file__=str(root/'worker.py')
 service.random.uniform=lambda *args:0
 service.serve()
''')
            env = {**os.environ, 'XDG_RUNTIME_DIR': str(root), 'HYPRLAND_INSTANCE_SIGNATURE':'fixture'}
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(str(runtime/'.socket2.sock')); server.listen(); server.settimeout(5)
                process = subprocess.Popen([sys.executable, str(wrapper)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                self.addCleanup(lambda: service.stop_worker(process))
                connection, _ = server.accept()
                try:
                    end = time.monotonic()+8
                    while not (root/'pids.json').exists() and time.monotonic()<end: time.sleep(.05)
                    self.assertTrue((root/'pids.json').exists(), 'Network worker did not start')
                    pids = json.loads((root/'pids.json').read_text())
                    # A second session helper must exit without another worker.
                    duplicate = subprocess.run([sys.executable, str(wrapper)], env=env, capture_output=True, timeout=4)
                    self.assertEqual(duplicate.returncode, 0)
                finally: connection.close()
                _, error = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, error.decode())
                for pid in pids:
                    path = Path('/proc')/str(pid)/'stat'
                    self.assertTrue(not path.exists() or path.read_text().split(') ')[1][0]=='Z', 'Session child survived logout')
                self.assertIn('paused at logout', json.loads((state/'status.json').read_text())['message'])

    def test_private_git_fallback_verifies_real_history_and_reuses_cache(self):
        with tempfile.TemporaryDirectory(prefix='xetal-git-history-') as directory:
            root = Path(directory); repo = root/'origin'; repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',*args], text=True).strip()
            git('init','-q','-b','main'); (repo/'code').write_text('one'); git('add','.');git('commit','-qm','First version'); first=git('rev-parse','HEAD')
            (repo/'code').write_text('two')
            (repo/'config/hypr').mkdir(parents=True)
            (repo/'config/hypr/VERSION').write_text('0.0.0.200-alpha\n')
            git('add','.');git('commit','-qm','Second version'); second=git('rev-parse','HEAD')
            with patch.object(github,'REPOSITORY',str(repo)):
                value=github.git_latest(first,cache=root/'cache')
                self.assertEqual(value['sha'],second);self.assertEqual(value['relation'],'ahead')
                self.assertEqual(value['message'],'Second version')
                self.assertEqual(value['release_version'],'0.0.0.200-alpha')
                with patch.object(github,'git_cache',side_effect=AssertionError('Unchanged head should not download again')):
                    self.assertEqual(github.git_latest(first,value,root/'cache')['relation'],'ahead')
                git('update-ref','refs/heads/main',first)
                self.assertEqual(github.git_latest(second,cache=root/'cache')['relation'],'behind')
                git('checkout','-q','--orphan','other');git('commit','-qm','Unrelated history'); other=git('rev-parse','HEAD')
                git('update-ref','refs/heads/main',other)
                self.assertEqual(github.git_latest(second,cache=root/'cache')['relation'],'diverged')


if __name__=='__main__':unittest.main()
