"""Read the public main branch; download only the exact advertised commit."""
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from update_engine import REPOSITORY, revision

API = 'https://api.github.com/repos/XetalEngine/x_hyperland'


def git_environment():
    return {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never',
            'GIT_ASKPASS': '/usr/bin/false', 'SSH_ASKPASS': '/usr/bin/false'}


def git_cache(cache):
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    bare = cache/'repository.git'
    if bare.is_symlink(): raise ValueError('Update cache must not be a symbolic link.')
    command = ['git', '-c', 'core.hooksPath=/dev/null']
    if not bare.exists(): subprocess.run([*command, 'init', '--bare', '-q', str(bare)], check=True, env=git_environment(), timeout=30)
    return bare, [*command, '--git-dir='+str(bare)]


def git_latest(current, previous=None, cache=None):
    """Existing Git credentials support the private repository before release.

    Credentials stay with Git's normal helper; they are never read or saved here.
    """
    previous = previous or {}; env = git_environment()
    output = subprocess.check_output(['git', 'ls-remote', '--exit-code', REPOSITORY, 'refs/heads/main'],
                                     env=env, text=True, timeout=30, stderr=subprocess.PIPE)
    commit = revision(output.split()[0])
    if previous.get('sha') == commit and previous.get('base') == current:
        return {**previous, 'transport': 'git'}
    value = {'sha':commit, 'base':current, 'etag':'', 'transport':'git',
             'relation':'identical', 'message':'Current GitHub main version'}
    if commit == current: return value
    _, command = git_cache(cache or Path.home()/'.cache/xetal-hyprland/updates')
    subprocess.run([*command, 'fetch', '--depth=256', '--no-tags', REPOSITORY, commit, current],
                   env=env, check=True, timeout=300, capture_output=True)
    def ancestor(a, b):
        result = subprocess.run([*command, 'merge-base', '--is-ancestor', a, b], env=env, capture_output=True)
        if result.returncode > 1: raise RuntimeError('Could not verify the update history.')
        return result.returncode == 0
    if not ancestor(current,commit) and not ancestor(commit,current):
        shallow = subprocess.check_output([*command, 'rev-parse', '--is-shallow-repository'], env=env, text=True).strip()
        if shallow == 'true':
            subprocess.run([*command, 'fetch', '--unshallow', '--no-tags', REPOSITORY, commit, current],
                           env=env, check=True, timeout=300, capture_output=True)
    value['relation'] = 'ahead' if ancestor(current,commit) else 'behind' if ancestor(commit,current) else 'diverged'
    value['message'] = subprocess.check_output([*command, 'show', '-s', '--format=%B', commit], env=env, text=True)[:4000].strip()
    return value


class RetryLater(RuntimeError):
    def __init__(self, message, retry_at): super().__init__(message); self.retry_at = retry_at


def request(route, etag=None):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'Xetal-Hyprland-Updater/1',
               'X-GitHub-Api-Version': '2026-03-10'}
    if etag: headers['If-None-Match'] = etag
    try:
        with urlopen(Request(API+route, headers=headers), timeout=20) as response:
            data = response.read(8_000_001)
            if len(data) > 8_000_000: raise ValueError('GitHub returned an unexpectedly large response.')
            return json.loads(data), response.headers.get('ETag', '')
    except HTTPError as error:
        if error.code == 304: return None, etag
        if error.code in (403, 429):
            try:
                retry = max(time.time()+60, float(error.headers.get('X-RateLimit-Reset', 0)),
                            time.time()+float(error.headers.get('Retry-After', 0)))
            except ValueError: retry = time.time()+900
            raise RetryLater('GitHub is busy. Update checks will resume automatically.', retry) from error
        raise


def latest(current, previous=None):
    previous = previous or {}; revision(current)
    if previous.get('transport') == 'git': return git_latest(current, previous)
    try: data, etag = request('/commits?sha=main&per_page=1', previous.get('etag'))
    except HTTPError as error:
        if error.code != 404: raise
        return git_latest(current, previous)
    if data is None:
        if not previous.get('sha'): raise ValueError('GitHub cache has no commit; check again.')
        result = dict(previous)
    else:
        if not isinstance(data, list) or not data: raise ValueError('GitHub did not return a release commit.')
        item = data[0]
        result = {'sha': revision(item['sha']), 'message': str(item['commit']['message'])[:4000], 'etag': etag}
    if result['sha'] == current: result['relation'] = 'identical'
    elif previous.get('base') == current and previous.get('sha') == result['sha'] and previous.get('relation'):
        result['relation'] = previous['relation']
    else:
        comparison, _ = request('/compare/'+current+'...'+result['sha'])
        result['relation'] = comparison['status']
        if result['relation'] not in ('ahead', 'behind', 'diverged', 'identical'):
            raise ValueError('GitHub returned an unknown commit relationship.')
    result['base'] = current
    return result


def source(commit, cache, destination):
    revision(commit); bare, command = git_cache(cache); env = git_environment()
    subprocess.run([*command, 'fetch', '--depth=1', '--no-tags', REPOSITORY, commit], check=True, env=env, timeout=300)
    actual = subprocess.check_output([*command, 'rev-parse', 'FETCH_HEAD'], env=env, text=True).strip()
    if actual != commit: raise ValueError('Downloaded commit does not match the update notice.')
    archive = destination.parent/'source.tar'
    with archive.open('wb') as stream:
        subprocess.run([*command, 'archive', '--format=tar', commit], stdout=stream, check=True, env=env, timeout=90)
    destination.mkdir(mode=0o700)
    total = 0
    with tarfile.open(archive) as stream:
        for member in stream:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isdir() or member.isfile()):
                raise ValueError('Update source contains an unsupported archive entry.')
            total += member.size
            if total > 512_000_000: raise ValueError('Update source is larger than the allowed download size.')
            target = destination.joinpath(*path.parts)
            if member.isdir(): target.mkdir(parents=True, exist_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with stream.extractfile(member) as src, target.open('wb') as dst: shutil.copyfileobj(src, dst)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
    # The installer verifies this revision as well. Keep a minimal local Git view
    # pointing at our private object store, never the developer's working clone.
    subprocess.run(['git', 'init', str(destination)], check=True, env=env, timeout=30)
    objects = destination/'.git/objects/info/alternates'; objects.parent.mkdir(parents=True, exist_ok=True)
    objects.write_text(str(bare.resolve()/'objects')+'\n')
    (destination/'.git/HEAD').write_text(commit+'\n')
    return destination
