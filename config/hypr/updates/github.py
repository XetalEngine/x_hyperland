"""Read the public main branch; download only the exact advertised commit."""
import base64
import binascii
from contextlib import contextmanager
import fcntl
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
import release_version

API = 'https://api.github.com/repos/XetalEngine/x_hyperland'
NOTES_UNAVAILABLE = 'Could not load all commit notes. Choose Check now to try again.'


def cached_notes(previous, current, commit):
    """A complete changelog belongs to both ends of an immutable commit range."""
    return (previous.get('base') == current and previous.get('sha') == commit
            and previous.get('notes_complete') is True
            and isinstance(previous.get('commits'), list)
            and bool(previous['commits']))


def git_environment():
    return {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never',
            'GIT_ASKPASS': '/usr/bin/false', 'SSH_ASKPASS': '/usr/bin/false'}


@contextmanager
def git_cache(cache):
    """Serialize source operations, including Git children surviving their parent.

    The new namespace excludes older workers that do not hold this lease. Never
    unlink the lease or explicitly unlock it: an inherited descriptor must keep
    recovery out until the last Git child has exited. Background maintenance is
    disabled so no detached writer can outlive that ownership.
    """
    private = cache/'git-v2'
    if private.is_symlink(): raise ValueError('Update cache must not be a symbolic link.')
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    lease = private/'operation.lock'
    descriptor = os.open(lease, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a+b') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another update download is still running. Please try again when it finishes.') from None
        bare = private/'repository.git'
        if bare.is_symlink(): raise ValueError('Update cache must not be a symbolic link.')
        # With the lease held, every Git lock here belongs to interrupted work.
        abandoned = sorted(bare.rglob('*.lock'))
        for path in abandoned:
            if path.is_symlink() or not path.is_file():
                raise ValueError('Update cache contains an unsupported lock entry.')
        for path in abandoned: path.unlink()
        if abandoned: print('Recovered an interrupted source download. Retrying safely…', flush=True)
        command = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'gc.auto=0', '-c', 'maintenance.auto=false']
        options = {'env': git_environment(), 'pass_fds': (lock.fileno(),)}
        # Reinitialization also completes an init interrupted before its first fetch.
        subprocess.run([*command, 'init', '--bare', '-q', str(bare)], check=True, timeout=30, **options)
        yield bare, [*command, '--git-dir='+str(bare)], options


def git_latest(current, previous=None, cache=None):
    """Existing Git credentials support the private repository before release.

    Credentials stay with Git's normal helper; they are never read or saved here.
    """
    previous = previous or {}; env = git_environment()
    output = subprocess.check_output(['git', 'ls-remote', '--exit-code', REPOSITORY, 'refs/heads/main'],
                                     env=env, text=True, timeout=30, stderr=subprocess.PIPE)
    commit = revision(output.split()[0])
    if (previous.get('sha') == commit and previous.get('base') == current and previous.get('relation') != 'unknown'
            and ('release_version' in previous or commit == current)
            and (previous.get('relation') != 'ahead' or cached_notes(previous, current, commit))):
        return {**previous, 'transport': 'git'}
    value = {'sha':commit, 'base':current, 'etag':'', 'transport':'git',
             'relation':'identical', 'message':'Current GitHub main version'}
    if commit == current: return value
    with git_cache(cache or Path.home()/'.cache/xetal-hyprland/updates') as (_, command, options):
        return git_history(current, commit, value, command, options)


def git_history(current, commit, value, command, options):
    subprocess.run([*command, 'fetch', '--depth=256', '--no-tags', REPOSITORY, commit],
                   check=True, timeout=300, capture_output=True, **options)
    version = subprocess.run([*command, 'show', commit+':'+release_version.SOURCE_PATH],
                             capture_output=True, text=True, timeout=30, **options)
    try: value['release_version'] = release_version.parse(version.stdout) if version.returncode == 0 else ''
    except ValueError: value['release_version'] = ''
    present = subprocess.run([*command, 'cat-file', '-e', current+'^{commit}'], capture_output=True, **options)
    if present.returncode:
        try:
            subprocess.run([*command, 'fetch', '--depth=256', '--no-tags', REPOSITORY, current],
                           check=True, timeout=300, capture_output=True, **options)
        except subprocess.CalledProcessError:
            return {**value, 'relation':'unknown',
                    'message':'This local desktop revision is not available from GitHub. Automatic downgrades are disabled.'}
    def ancestor(a, b):
        result = subprocess.run([*command, 'merge-base', '--is-ancestor', a, b], capture_output=True, **options)
        if result.returncode > 1: raise RuntimeError('Could not verify the update history.')
        return result.returncode == 0
    if not ancestor(current,commit) and not ancestor(commit,current):
        shallow = subprocess.check_output([*command, 'rev-parse', '--is-shallow-repository'], text=True, **options).strip()
        if shallow == 'true':
            subprocess.run([*command, 'fetch', '--unshallow', '--no-tags', REPOSITORY, commit, current],
                           check=True, timeout=300, capture_output=True, **options)
    value['relation'] = 'ahead' if ancestor(current,commit) else 'behind' if ancestor(commit,current) else 'diverged'
    value['message'] = subprocess.check_output([*command, 'show', '-s', '--format=%B', commit], text=True, **options).strip()
    value.update(commits=[], notes_complete=value['relation'] != 'ahead')
    if value['relation'] == 'ahead':
        try:
            value['commits'] = git_notes(current, commit, command, options)
            value['notes_complete'] = True
        except (OSError, ValueError, subprocess.SubprocessError):
            # Display metadata must not invalidate an already verified update.
            value['notes_error'] = NOTES_UNAVAILABLE
    return value


def git_notes(current, commit, command, options):
    # Knowing that the installed commit is an ancestor does not prove a shallow
    # log includes every merged branch. Complete the history before listing it.
    shallow = subprocess.check_output([*command, 'rev-parse', '--is-shallow-repository'],
                                      text=True, timeout=30, **options).strip()
    if shallow == 'true':
        subprocess.run([*command, 'fetch', '--unshallow', '--no-tags', REPOSITORY, commit, current],
                       check=True, timeout=300, capture_output=True, **options)
    output = subprocess.check_output([*command, 'log', '--date-order', '-z', '--format=%H%x00%cI%x00%B',
                                      current+'..'+commit], text=True, timeout=30, **options)
    fields = output.split('\0')
    if fields[-1] == '': fields.pop()
    if not fields or len(fields) % 3: raise ValueError('Incomplete Git commit notes.')
    commits = [{'sha': revision(fields[i]), 'date': fields[i+1], 'message': fields[i+2].strip()}
               for i in range(0, len(fields), 3)]
    if current in {item['sha'] for item in commits} or commit not in {item['sha'] for item in commits}:
        raise ValueError('Git commit notes do not match the update range.')
    return commits


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
        result = {'sha': revision(item['sha']), 'message': str(item['commit']['message']), 'etag': etag}
    # A 304 may reuse the head while the installed version has moved forward.
    # Never carry that older range's notes into the new comparison.
    for key in ('commits', 'notes_complete', 'notes_error'): result.pop(key, None)
    comparison = None
    if result['sha'] == current: result['relation'] = 'identical'
    elif (previous.get('base') == current and previous.get('sha') == result['sha'] and
          previous.get('relation') in ('ahead', 'behind', 'diverged', 'identical')):
        result['relation'] = previous['relation']
    else:
        try: comparison, _ = request('/compare/'+current+'...'+result['sha']+'?per_page=100&page=1')
        except HTTPError as error:
            if error.code != 404: raise
            return with_version({**result,'base':current,'relation':'unknown',
                    'message':'This local desktop revision is not available from GitHub. Automatic downgrades are disabled.'}, previous)
        result['relation'] = comparison['status']
        if result['relation'] not in ('ahead', 'behind', 'diverged', 'identical'):
            raise ValueError('GitHub returned an unknown commit relationship.')
    result['base'] = current
    result.update(commits=[], notes_complete=result['relation'] != 'ahead')
    if result['relation'] == 'ahead':
        if cached_notes(previous, current, result['sha']):
            result.update(commits=previous['commits'], notes_complete=True)
        else:
            try:
                result.update(commits=compare_notes(current, result['sha'], comparison), notes_complete=True)
            except (OSError, ValueError, KeyError, TypeError, RetryLater):
                result['notes_error'] = NOTES_UNAVAILABLE
    return with_version(result, previous)


def compare_notes(current, commit, first_page=None):
    """Fetch every page for the pinned range; GitHub orders it oldest first."""
    commits, seen = [], set()
    page, total = 1, None
    while True:
        if page == 1 and first_page is not None:
            data = first_page
        else:
            data, _ = request('/compare/'+current+'...'+commit+'?per_page=100&page='+str(page))
        count = data.get('total_commits') if isinstance(data, dict) else None
        items = data.get('commits') if isinstance(data, dict) else None
        if (type(count) is not int or count < 1 or not isinstance(items, list) or not items
                or data.get('status') != 'ahead' or (total is not None and count != total)):
            raise ValueError('GitHub returned incomplete commit notes.')
        total = count
        for item in items:
            sha = revision(item['sha'])
            message = item['commit']['message']
            if sha == current or sha in seen or not isinstance(message, str):
                raise ValueError('GitHub commit notes do not match the update range.')
            seen.add(sha)
            committer = item['commit'].get('committer')
            if not isinstance(committer, dict): committer = {}
            commits.append({'sha': sha, 'message': message.strip(), 'date': str(committer.get('date') or '')})
        if len(commits) >= total:
            if len(commits) != total or commit not in seen:
                raise ValueError('GitHub commit notes do not match the update range.')
            return list(reversed(commits))
        page += 1


def with_version(result, previous):
    """Read the label at this exact commit, never at a moving branch head."""
    if previous.get('sha') == result['sha'] and 'release_version' in previous:
        return {**result, 'release_version': previous['release_version']}
    try:
        data, _ = request('/contents/'+release_version.SOURCE_PATH+'?ref='+result['sha'])
        if not isinstance(data, dict) or data.get('type') != 'file' or data.get('encoding') != 'base64':
            return result
        encoded = data.get('content', '')
        if not isinstance(encoded, str) or len(encoded) > 256: return result
        value = release_version.parse(base64.b64decode(encoded).decode('utf-8'))
        return {**result, 'release_version': value}
    except HTTPError as error:
        if error.code == 404: return {**result, 'release_version': ''}
    except (OSError, ValueError, binascii.Error, RetryLater):
        pass
    # Optional display metadata must not prevent a verified commit update.
    return result


def source(commit, cache, destination):
    revision(commit)
    with git_cache(cache) as (bare, command, options):
        return checkout(commit, bare, command, options, destination)


def checkout(commit, bare, command, options, destination):
    subprocess.run([*command, 'fetch', '--depth=1', '--no-tags', REPOSITORY, commit], check=True, timeout=300, **options)
    actual = subprocess.check_output([*command, 'rev-parse', 'FETCH_HEAD'], text=True, **options).strip()
    if actual != commit: raise ValueError('Downloaded commit does not match the update notice.')
    archive = destination.parent/'source.tar'
    with archive.open('wb') as stream:
        subprocess.run([*command, 'archive', '--format=tar', commit], stdout=stream, check=True, timeout=90, **options)
    destination.mkdir(mode=0o700)
    with tarfile.open(archive) as stream:
        for member in stream:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isdir() or member.isfile()):
                raise ValueError('Update source contains an unsupported archive entry.')
            target = destination.joinpath(*path.parts)
            if member.isdir(): target.mkdir(parents=True, exist_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with stream.extractfile(member) as src, target.open('wb') as dst: shutil.copyfileobj(src, dst)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
    # The installer verifies this revision as well. Keep a minimal local Git view
    # pointing at our private object store, never the developer's working clone.
    subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', 'init', '--quiet', '--initial-branch=main', str(destination)],
                   check=True, timeout=30, **options)
    objects = destination/'.git/objects/info/alternates'; objects.parent.mkdir(parents=True, exist_ok=True)
    objects.write_text(str(bare.resolve()/'objects')+'\n')
    (destination/'.git/HEAD').write_text(commit+'\n')
    return destination
