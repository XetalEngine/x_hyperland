"""Recognize exact release files copied into a profile before registration.

Unknown local contents remain a conflict. Only ancestors of the exact incoming
commit are consulted, and no developer checkout or installed inventory is edited.
"""
from pathlib import Path
import subprocess

import github
import update_engine as engine

DEPTH = 64
MAX_TEXT = 2_000_000


class ReleaseFiles:
    def __init__(self, source, commit, home, cache=None):
        self.source = Path(source)
        self.commit = engine.revision(commit)
        self.home = Path(home)
        self.cache = cache or self.home/'.cache/xetal-hyprland/updates'
        self.command = ['git', '-c', 'core.hooksPath=/dev/null', '--literal-pathspecs', '-C', str(self.source)]
        self.commits = None

    def run(self, *args):
        return subprocess.run([*self.command, *args], capture_output=True, timeout=30,
                              env=github.git_environment())

    def history(self):
        if self.commits is not None: return self.commits
        # Archives and the downloader's minimal checkout may lack ancestors.
        # Fetch history only when a collision needs it, into our private cache.
        result = self.run('rev-list', '--first-parent', f'--max-count={DEPTH}', self.commit)
        shallow = self.run('rev-parse', '--is-shallow-repository')
        if result.returncode or shallow.stdout.strip() == b'true':
            _, self.command = github.git_cache(self.cache)
            self.command.insert(1, '--literal-pathspecs')
            subprocess.run([*self.command, 'fetch', f'--depth={DEPTH}', '--no-tags',
                            github.REPOSITORY, self.commit], check=True, capture_output=True,
                           timeout=300, env=github.git_environment())
            result = self.run('rev-list', '--first-parent', f'--max-count={DEPTH}', self.commit)
        if result.returncode: raise RuntimeError('Could not verify earlier release files. Your local files were kept.')
        self.commits = [engine.revision(line) for line in result.stdout.decode().splitlines()]
        if not self.commits or self.commits[0] != self.commit:
            raise RuntimeError('Release file history does not match the incoming update.')
        return self.commits

    def __call__(self, name, local):
        engine.location(self.source/'config/hypr', name)
        if len(local) > MAX_TEXT or b'\0' in local: return False
        try: local.decode('utf-8')
        except UnicodeDecodeError: return False
        path = 'config/hypr/'+name
        seen = set()
        for commit in self.history():
            result = self.run('ls-tree', '-z', commit, '--', path)
            if result.returncode: raise RuntimeError('Could not verify earlier release file: '+name)
            if not result.stdout: continue
            record, _, actual_path = result.stdout.rstrip(b'\0').partition(b'\t')
            fields = record.split()
            if (len(fields) != 3 or fields[0] not in (b'100644', b'100755')
                    or fields[1] != b'blob' or actual_path.decode() != path): continue
            blob = fields[2].decode()
            if blob in seen: continue
            seen.add(blob)
            size = self.run('cat-file', '-s', blob)
            if size.returncode or int(size.stdout) > MAX_TEXT: continue
            contents = self.run('cat-file', 'blob', blob)
            if contents.returncode: raise RuntimeError('Could not read earlier release file: '+name)
            if contents.stdout == local: return True
            try:
                rendered = contents.stdout.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
                rendered = rendered.replace('@HOME@', str(self.home)).replace('@HYPR@', str(self.home/'.config/hypr'))
                if rendered.encode() == local: return True
            except UnicodeDecodeError: pass
        return False
