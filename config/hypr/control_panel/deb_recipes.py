"""Small, explicit Arch adaptations; never execute Debian maintainer scripts.

Chrome's native layout follows the maintained google-chrome AUR recipe:
https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=google-chrome
"""
import argparse
from pathlib import Path
import shutil
import subprocess

from deb_dependencies import parse_relationships

CHROME = 'google-chrome-stable'
CHROME_EXTRAS = ('libxss', 'libxtst', 'hicolor-icon-theme', 'desktop-file-utils')
CHROME_CRON = ('etc/cron.daily/google-chrome', 'opt/google/chrome/cron/google-chrome')


def dependency_fields(fields):
    result = dict(fields)
    if fields['package'] == CHROME:
        # dpkg is Google's DEBIAN installation prerequisite. This recipe replaces
        # those scripts with a pacman layout, not a runtime Debian environment.
        groups = parse_relationships(fields.get('pre-depends', ''))
        if len(groups) == 1 and len(groups[0]) == 1 and groups[0][0].name == 'dpkg':
            result.pop('pre-depends', None)
        result['depends'] = ', '.join(filter(None, [fields.get('depends', ''), *CHROME_EXTRAS]))
    return result


def omitted_application_files(name):
    return {'opt/google/chrome/cron/google-chrome'} if name == CHROME else set()


def chrome_layout(root):
    app = root/'opt/google/chrome'
    if not (app/'chrome').is_file() or not (root/'usr/share/applications/google-chrome.desktop').is_file():
        raise RuntimeError('The Chrome package layout changed; its Arch recipe must be reviewed.')
    # Install icons as package-owned files. Arch's icon/desktop-file hooks do
    # the cache refresh. Keep original /opt logos for payload verification.
    for size in (16, 24, 32, 48, 64, 128, 256):
        source = app/f'product_logo_{size}.png'
        if not source.is_file():
            raise RuntimeError('The Chrome icon layout changed; missing '+str(source))
        target = root/f'usr/share/icons/hicolor/{size}x{size}/apps/google-chrome.png'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o644)
    # These are Google's apt-repository maintenance scripts, not the browser.
    # Remove only the two known paths; leave unrelated cron files alone.
    for relative in CHROME_CRON:
        path = root/relative
        path.unlink(missing_ok=True)
        try:
            path.parent.rmdir()
        except OSError:
            pass
    # Debtap's shell translation corrupts Google's heredocs and conditionals.
    # Chrome needs none of those Debian setup/removal actions on Arch.
    (root/'.INSTALL').write_text('# Chrome uses native pacman icon and desktop-file hooks.\n')


def finalize(root, name):
    if name == CHROME:
        chrome_layout(root)
    script = root/'.INSTALL'
    if script.exists():
        result = subprocess.run(['bash', '-n', str(script)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('Debtap generated an invalid installation script. '
                               'This application needs an Arch recipe; nothing was installed.\n'
                               + result.stderr.strip())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    try:
        finalize(args.root, args.package)
    except (OSError, RuntimeError) as error:
        parser.exit(1, str(error)+'\n')
