"""Resolve the signed Arch runtime and desktop as one native transaction."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.request import urlopen

import runtime_install as runtime

REPOSITORY = 'xetal-fusion-runtime'
ENV = {**os.environ, 'LC_ALL':'C'}


def target():
    return runtime.policy.arch_manifest()


def expected(required=None):
    return {p['name']:p['version'] for p in (required or target())['packages']}


def hold_text(required=None):
    required = required or target()
    return '# Managed by Xetal Setup: Hyprland '+required['hyprland']+' and matching libraries\nIgnorePkg = '+ ' '.join(expected(required))+'\n'


def pinned():
    try:
        return (runtime.PIN.read_text() == hold_text()
                and set(expected()) <= set(runtime.pacman_config('IgnorePkg')))
    except OSError:
        return False


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def packages(cache=None, required=None):
    """Use signed release files, cached files, or the exact official archive."""
    required = required or target()
    cache = cache or Path.home()/'.cache/xetal-hyprland/arch-runtime'
    result = []
    for item in required['packages']:
        sources = [runtime.BUNDLED, runtime.BUNDLED/'arch', cache, *runtime.package_caches()]
        paths = []
        for suffix, key in (('', 'sha256'), ('.sig', 'signature_sha256')):
            name = item['file']+suffix
            path = next((p/name for p in sources if (p/name).is_file() and digest(p/name) == item[key]), None)
            if path is None:
                cache.mkdir(parents=True, exist_ok=True)
                path = cache/name
                url = 'https://archive.archlinux.org/packages/'+item['name'][0]+'/'+item['name']+'/'+name
                print('Downloading matching runtime: '+name, flush=True)
                fd, temporary = tempfile.mkstemp(dir=cache, prefix='.download-')
                try:
                    with os.fdopen(fd, 'wb') as output, urlopen(url, timeout=90) as source:
                        shutil.copyfileobj(source, output)
                    if digest(Path(temporary)) != item[key]:
                        raise RuntimeError('Arch runtime checksum failed: '+name)
                    os.replace(temporary, path)
                finally:
                    Path(temporary).unlink(missing_ok=True)
            paths.append(path)
        result.append((item, *paths))
    return result


def repository(directory, required=None, verify=False):
    """Generate a private repository from verified, unmodified signed packages."""
    required = required or target()
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for item, package, signature in packages(required=required):
        saved = directory/item['file']
        for source, destination, key in ((package, saved, 'sha256'),
                                        (signature, Path(str(saved)+'.sig'), 'signature_sha256')):
            shutil.copyfile(source, destination)
            if digest(destination) != item[key]:
                raise RuntimeError('Arch runtime changed while staging: '+destination.name)
        if verify:
            subprocess.run(['/usr/bin/pacman-key', '--verify', str(saved)+'.sig', str(saved)], check=True)
            identity = subprocess.run(['/usr/bin/pacman', '-Qp', str(saved)], check=True,
                                      capture_output=True, text=True, env=ENV).stdout.strip()
            if identity != item['name']+' '+item['version']:
                raise RuntimeError('Unexpected Arch runtime package: '+saved.name)
        paths.append(str(saved))
    result = subprocess.run(['repo-add', '--include-sigs', str(directory/(REPOSITORY+'.db.tar.gz')), *paths],
                            capture_output=True, text=True, env=ENV)
    if result.returncode:
        raise RuntimeError('Could not prepare the matching runtime repository.\n'+runtime.package_error_output(result))
    return directory/(REPOSITORY+'.db')


def configuration(text, directory):
    """Prepend the private repository without editing the user's repositories."""
    sections = list(re.finditer(r'^\[([^\]\n]+)\]\s*$', text, re.M))
    if not sections or sections[0][1] != 'options' or any(s[1] == REPOSITORY for s in sections):
        raise RuntimeError('Unexpected pacman repository configuration.')
    start = sections[1].start() if len(sections) > 1 else len(text)
    # DatabaseNever applies only to our generated, hash-verified local index.
    # Every package still requires its original trusted distro signature.
    local = ('\n['+REPOSITORY+']\nSigLevel = PackageRequired DatabaseNever\n'
             'Usage = Search Install Upgrade\nServer = '+directory.as_uri()+'\n\n')
    return text[:start]+local+text[start:]


def package_args(desktop, required=None):
    names = expected(required)
    return [*(REPOSITORY+'/'+name for name in names), *(name for name in desktop if name not in names)]


def resolve(config, desktop, prefix=(), required=None):
    result = subprocess.run(['pacman', '--config', str(config), *prefix, '-Sup', '--noconfirm',
                             '--print-format', '%n %v', *package_args(desktop, required)],
                            capture_output=True, text=True, timeout=180, env=ENV)
    if result.returncode:
        raise RuntimeError('The matching runtime and desktop dependencies could not be resolved together. '
                           'No packages have been changed.\n'+runtime.package_error_output(result))
    selected = dict(line.split() for line in result.stdout.splitlines() if len(line.split()) == 2)
    import dependencies
    problems = dependencies.package_version_problems(result.stdout)
    if problems:
        raise RuntimeError('\n'.join(problems))
    if any(selected.get(name) != version for name, version in expected(required).items()):
        raise RuntimeError('Pacman did not select the complete matching runtime.')
    return selected


def refresh_metadata(directory, repositories=None):
    """Refresh only the disposable preflight database; never pacman's host DB."""
    directory.mkdir(parents=True, exist_ok=True)
    repositories = repositories or [(name, runtime.pacman_config('--repo', name, 'Server'))
                                    for name in runtime.pacman_config('--repo-list')]
    for name, servers in repositories:
        if not re.fullmatch(r'[A-Za-z0-9_.+-]+', name):
            raise RuntimeError('Invalid repository name.')
        print('Checking current package repository: '+name, flush=True)
        failure = None
        for server in servers[:5]:
            try:
                with urlopen(server.rstrip('/')+'/'+name+'.db', timeout=30) as source, (directory/(name+'.db')).open('wb') as output:
                    shutil.copyfileobj(source, output)
                break
            except OSError as error:
                failure = error
        else:
            raise RuntimeError('Cannot refresh package availability for '+name+'. Check the network and configured mirrors.') from failure


def preflight(desktop):
    with tempfile.TemporaryDirectory(prefix='xetal-arch-preflight-') as temp:
        root = Path(temp)
        # Keep the real installed package state: tests must also cover older
        # libraries and reverse dependencies, not just an empty installation.
        db = root/'db'
        local = Path((runtime.pacman_config('DBPath') or ['/var/lib/pacman'])[0])/'local'
        shutil.copytree(local, db/'local')
        refresh_metadata(db/'sync')
        index = repository(root/'runtime')
        shutil.copyfile(index, db/'sync'/index.name)
        base = subprocess.run(['pacman-conf'], capture_output=True, text=True, check=True).stdout
        config = root/'pacman.conf'
        config.write_text(configuration(base, root/'runtime'))
        (root/'cache').mkdir()
        return resolve(config, desktop, ['--dbpath', str(db), '--cachedir', str(root/'cache'),
                                        '--logfile', str(root/'pacman.log')])


def ensure(yes=False, force=False):
    if (not force and not runtime.policy.problem() and pinned()
            and runtime.policy.arch_versions(expected()) == expected()):
        return False
    print('Installing Hyprland '+target()['hyprland']+' with its matching libraries and all desktop dependencies.\n'
          'Arch-family packages are upgraded together using your configured distribution repositories.', flush=True)
    if not yes and input('Install the matching runtime and coordinated package upgrade? [y/N] ').strip().lower() not in ('y', 'yes'):
        raise RuntimeError('Package setup cancelled.')
    packages()
    prefix = runtime.administrator()
    args = [*prefix, '/usr/bin/python3', str(runtime.ROOT/'installer/system_arch_runtime.py')]
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as process:
        try:
            for line in process.stdout:
                if line.startswith('XETAL_RUNTIME_TRANSACTION '):
                    runtime.TRANSACTION = Path(line.strip().split(' ', 1)[1])
                    runtime.TRANSACTION_BACKEND = 'arch-bundle'
                else:
                    print(line, end='', flush=True)
            code = process.wait()
        except KeyboardInterrupt:
            process.wait()
            raise
    runtime.check_administrator_result(prefix, code)
    if code:
        raise RuntimeError('Arch runtime/dependency installation failed. See the package details above.')
    runtime.policy.require()
    if not pinned() or runtime.policy.arch_versions(expected()) != expected():
        raise RuntimeError('The complete matching Arch runtime and package holds were not installed.')
    return bool(runtime.TRANSACTION)
