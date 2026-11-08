"""Translate declared Debian requirements before handing an application to pacman.

Names are explicit, never guessed by deleting digits. Unknown names must exist
in Arch under that exact name. Debian alternatives are alternatives, not a list
of extra packages to install. This is deliberately not a Debian environment.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import tempfile


# Debian ABI package names -> the Arch package containing the same component.
# Keep ABI generations explicit: e.g. libssl1.1 must NOT become openssl 3.
# Reference: the upstream Debian control field and Arch package/file databases.
ALIASES = {
    'fonts-liberation': 'ttf-liberation', 'fonts-dejavu-core': 'ttf-dejavu',
    'libasound2': 'alsa-lib', 'libasound2t64': 'alsa-lib',
    'libatk-bridge2.0-0': 'at-spi2-core', 'libatk-bridge2.0-0t64': 'at-spi2-core',
    'libatk1.0-0': 'at-spi2-core', 'libatk1.0-0t64': 'at-spi2-core',
    'libatspi2.0-0': 'at-spi2-core', 'libatspi2.0-0t64': 'at-spi2-core',
    'libc6': 'glibc', 'libcairo2': 'cairo', 'libcairo-gobject2': 'cairo',
    'libcups2': 'libcups', 'libcups2t64': 'libcups',
    'libcurl3-gnutls': 'libcurl-gnutls', 'libcurl4': 'curl', 'libcurl4t64': 'curl',
    'libdbus-1-3': 'dbus', 'libdrm2': 'libdrm', 'libexpat1': 'expat',
    'libfontconfig1': 'fontconfig', 'libfreetype6': 'freetype2',
    'libgbm1': 'mesa', 'libgl1': 'libglvnd', 'libegl1': 'libglvnd',
    'libglib2.0-0': 'glib2', 'libglib2.0-0t64': 'glib2',
    'libgtk-3-0': 'gtk3', 'libgtk-3-0t64': 'gtk3', 'libgtk-4-1': 'gtk4',
    'libnspr4': 'nspr', 'libnss3': 'nss', 'libpango-1.0-0': 'pango',
    'libpangocairo-1.0-0': 'pango', 'libpangoft2-1.0-0': 'pango',
    'libudev1': 'systemd-libs', 'libvulkan1': 'vulkan-icd-loader',
    'libx11-6': 'libx11', 'libx11-xcb1': 'libx11', 'libxcb1': 'libxcb',
    'libxcomposite1': 'libxcomposite', 'libxcursor1': 'libxcursor',
    'libxdamage1': 'libxdamage', 'libxext6': 'libxext', 'libxfixes3': 'libxfixes',
    'libxi6': 'libxi', 'libxinerama1': 'libxinerama', 'libxrandr2': 'libxrandr',
    'libxrender1': 'libxrender', 'libxss1': 'libxss', 'libxtst6': 'libxtst',
    'libxkbcommon0': 'libxkbcommon', 'libxkbcommon-x11-0': 'libxkbcommon-x11',
    'libwayland-client0': 'wayland', 'libwayland-cursor0': 'wayland',
    'libwayland-egl1': 'wayland', 'libzstd1': 'zstd', 'zlib1g': 'zlib',
    'liblzma5': 'xz', 'libbz2-1.0': 'bzip2', 'libsqlite3-0': 'sqlite',
    'libssl3': 'openssl', 'libssl3t64': 'openssl', 'libnotify4': 'libnotify',
    'libsecret-1-0': 'libsecret', 'libpulse0': 'libpulse',
    'libgcc-s1': 'gcc-libs', 'libstdc++6': 'gcc-libs',
    'python3': 'python', 'libfuse2': 'fuse2', 'libfuse2t64': 'fuse2',
    'libfuse3-3': 'fuse3',
}
ARCHITECTURES = {'x86_64': 'amd64', 'aarch64': 'arm64', 'i686': 'i386',
                 'armv7l': 'armhf'}
NAME = r'[a-z0-9][a-z0-9+.-]*'
ATOM = re.compile(rf'({NAME})(?::(any|native|{NAME}))?\s*'
                  r'(?:\(\s*(>=|<=|>>|<<|=)\s*([^\s()]+)\s*\))?')


def command(args):
    result = subprocess.run(args, capture_output=True, text=True,
                            env=dict(os.environ, LC_ALL='C'))
    if result.returncode:
        raise RuntimeError(f'{args[0]} could not inspect package metadata: '
                           + (result.stderr.strip() or result.stdout.strip()))
    return result.stdout


def control_fields(text):
    fields = {}
    key = None
    for line in text.splitlines():
        if line.startswith((' ', '\t')) and key:
            fields[key] += ' ' + line.strip()
        elif line:
            key, separator, value = line.partition(':')
            key = key.lower()
            if not separator or not re.fullmatch(r'[a-z][a-z0-9-]*', key) or key in fields:
                raise RuntimeError('Invalid or repeated Debian control field: ' + line)
            fields[key] = value.strip()
    if not all(fields.get(key) for key in ('package', 'version', 'architecture')):
        raise RuntimeError('The .deb control file is missing its package, version or architecture.')
    return fields


def read_control(deb):
    """Only stream the control file; do not extract or run maintainer scripts."""
    members = command(['ar', 't', str(deb)]).splitlines()
    matches = [name for name in members if re.fullmatch(
        r'control\.tar(?:\.(?:gz|xz|bz2|lzma|zst))?', name)]
    if len(matches) != 1:
        raise RuntimeError('The .deb must contain exactly one supported control archive.')
    with tempfile.TemporaryFile() as errors:
        with subprocess.Popen(['ar', 'p', str(deb), matches[0]], stdout=subprocess.PIPE,
                              stderr=errors) as reader:
            # bsdtar normalizes ./control and control for member selection.
            with subprocess.Popen(['bsdtar', '-xOf', '-', '--', 'control'],
                                  stdin=reader.stdout, stdout=subprocess.PIPE,
                                  stderr=errors) as unpacker:
                reader.stdout.close()
                data = unpacker.stdout.read(1024 * 1024 + 1)
                if len(data) > 1024 * 1024:
                    unpacker.kill()
                    reader.kill()
                    raise RuntimeError('The Debian control file is too large.')
                if unpacker.wait() or reader.wait():
                    errors.seek(0)
                    raise RuntimeError('Could not read Debian control metadata: '
                                       + errors.read().decode(errors='replace'))
    return control_fields(data.decode('utf-8'))


@dataclass(frozen=True)
class Requirement:
    name: str
    qualifier: str | None = None
    operator: str | None = None
    version: str | None = None


def parse_relationships(text):
    if not text.strip():
        return []
    groups = []
    for group in text.split(','):
        alternatives = []
        for raw in group.split('|'):
            match = ATOM.fullmatch(raw.strip())
            if not match:
                raise RuntimeError('Unsupported Debian dependency syntax: ' + raw.strip())
            alternatives.append(Requirement(*match.groups()))
        groups.append(alternatives)
    return groups


def upstream_version(version):
    # Debian and Arch epochs/revisions are maintained independently. Compare
    # upstream minimums, NOT Debian's 2:4.9-2~ with Arch's 4.40-1 verbatim.
    version = version.split(':', 1)[-1].rsplit('-', 1)[0]
    return version


def minimum(requirement):
    if not requirement.operator:
        return ''
    if requirement.operator != '>=':
        raise ValueError('exact versions and upper/strict bounds need a package-specific recipe')
    # Requiring the final upstream release is conservative for a beta/rc floor.
    value = upstream_version(requirement.version).split('~', 1)[0]
    if not re.fullmatch(r'[0-9][A-Za-z0-9.+_]*', value):
        raise ValueError('the Debian version cannot be compared with an Arch version')
    return value


class Repository:
    def __init__(self):
        self.local = {}
        self.sync = {}
        for line in command(['pacman', '-Q']).splitlines():
            name, version = line.split()
            self.local[name] = version
        for line in command(['pacman', '-Sl']).splitlines():
            _, name, version, *_ = line.split()
            # pacman repository priority, including an installed custom repo.
            self.sync.setdefault(name, version)

    def candidates(self, name):
        return [(self.local[name], True)] if name in self.local else []

    def available(self, name):
        return [(self.sync[name], False)] if name in self.sync else []

    def sufficient(self, version, floor):
        return not floor or int(command(['vercmp', upstream_version(version), floor]).strip()) >= 0


def resolve(fields, repository=None, machine=None):
    machine = machine or os.uname().machine
    native = ARCHITECTURES.get(machine)
    if fields['architecture'] not in ('all', native):
        raise RuntimeError(f"This .deb is for {fields['architecture']}; this system is {machine}. "
                           'Cross-architecture conversion is not supported.')
    groups = parse_relationships(fields.get('pre-depends', ''))
    groups += parse_relationships(fields.get('depends', ''))
    repository = repository or Repository()
    dependencies, rows, problems = [], [], []
    for alternatives in groups:
        reasons = []
        chosen = None
        # Keep a suitable installed alternative when one exists. Otherwise
        # prefer the first supported alternative in Debian's declared order.
        for installed in (True, False):
            for req in alternatives:
                try:
                    if req.qualifier not in (None, 'any', 'native', native):
                        raise ValueError('requires a foreign architecture')
                    floor = minimum(req)
                    target = ALIASES.get(req.name, req.name)
                    candidates = (repository.candidates(target) if installed
                                  else repository.available(target))
                    for version, _ in candidates:
                        if not repository.sufficient(version, floor):
                            continue
                        # Use Arch's epoch in the constraint; it is unrelated to
                        # the Debian epoch we removed above. Keep the minimum.
                        epoch = version.split(':', 1)[0] + ':' if ':' in version else ''
                        dependency = target + ('>=' + epoch + floor if floor else '')
                        chosen = dependency
                        rows.append(f'{req.name}' + (f' ({req.operator} {req.version})' if req.operator else '')
                                    + f' → {dependency} ({"installed" if installed else "repository"}: {version})')
                        break
                    if chosen:
                        break
                    reasons.append(f'{req.name} → {target}: missing or below its minimum version')
                except ValueError as error:
                    reasons.append(f'{req.name}: {error}')
            if chosen:
                break
        if chosen:
            if chosen not in dependencies:
                dependencies.append(chosen)
        else:
            problems.append(' | '.join(dict.fromkeys(reasons)))
    if problems:
        raise RuntimeError('Dependencies could not be mapped automatically; the application was not installed:\n  '
                           + '\n  '.join(problems)
                           + '\nAn unavailable dependency needs an explicit Arch mapping or package-specific recipe. '
                           'Dependency checks have not been bypassed.')
    return dependencies, rows
