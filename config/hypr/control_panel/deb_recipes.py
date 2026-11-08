"""Small, explicit Arch adaptations; never execute Debian maintainer scripts.

Chrome's native layout follows the maintained google-chrome AUR recipe:
https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=google-chrome
"""
import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess

from deb_dependencies import parse_relationships

CHROME = 'google-chrome-stable'
CHROME_EXTRAS = ('libxss', 'libxtst', 'hicolor-icon-theme', 'desktop-file-utils')
CHROME_CRON = ('etc/cron.daily/google-chrome', 'opt/google/chrome/cron/google-chrome')
VSCODE = 'code'
VSCODE_EXTRAS = ('desktop-file-utils', 'gtk-update-icon-cache', 'hicolor-icon-theme', 'shared-mime-info')


def dependency_fields(fields):
    result = dict(fields)
    if fields['package'] == CHROME:
        # dpkg is Google's DEBIAN installation prerequisite. This recipe replaces
        # those scripts with a pacman layout, not a runtime Debian environment.
        groups = parse_relationships(fields.get('pre-depends', ''))
        if len(groups) == 1 and len(groups[0]) == 1 and groups[0][0].name == 'dpkg':
            result.pop('pre-depends', None)
        result['depends'] = ', '.join(filter(None, [fields.get('depends', ''), *CHROME_EXTRAS]))
    elif fields['package'] == VSCODE:
        # Native transaction hooks refresh the packaged desktop, icon and MIME
        # entries on installation, upgrade and removal.
        result['depends'] = ', '.join(filter(None, [fields.get('depends', ''), *VSCODE_EXTRAS]))
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
    # Pacman replaces files on reinstall, but retains existing directory
    # permissions. Repair the 0700 directories left by our former umask bug.
    # Use only public 0755 directories in this Chrome payload, never recurse,
    # follow symlinks, change ownership, or broaden a private vendor directory.
    public=[]
    for path in sorted(root.rglob('*')):
        if path.is_dir() and not path.is_symlink() and path.stat().st_mode&0o7777==0o755:
            name=path.relative_to(root).as_posix()
            if name == 'opt/google' or name.startswith(('opt/google/','usr/share/')):
                public.append(name)
    # Debtap's shell translation corrupts Google's heredocs and conditionals.
    # Replace those Debian actions with this narrow native repair; Arch hooks
    # already handle desktop/icon caches. This runs on install and reinstall.
    (root/'.INSTALL').write_text('''# Chrome uses native pacman icon and desktop-file hooks.
post_install() {
    local directory
    for directory in '''+' '.join(shlex.quote('/'+name) for name in public)+'''; do
        if [ "$(stat -c '%a:%u' -- "$directory" 2>/dev/null)" = "700:0" ] &&
           [ "$(realpath -e -- "$directory" 2>/dev/null)" = "$directory" ]; then
            chmod 0755 -- "$directory" || return 1
            printf 'Restored Chrome directory permissions: %s\\n' "$directory"
        fi
    done
}
post_upgrade() { post_install; }
''')


def vscode_layout(root):
    """Replace VS Code Stable's Debian setup with package-owned Arch files."""
    required = ('usr/share/code/code', 'usr/share/code/bin/code',
                'usr/share/code/resources/app/out/cli.js',
                'usr/share/code/resources/app/product.json',
                'usr/share/applications/com.microsoft.VSCode.desktop',
                'usr/share/applications/com.microsoft.VSCode.UrlHandler.desktop',
                'usr/share/pixmaps/vscode.png', 'usr/share/mime/packages/code-workspace.xml')
    icon = root/'usr/share/icons/hicolor/1024x1024/apps/vscode.png'
    launcher = root/'usr/bin/code'
    # A changed layout needs review. Never follow an archive symlink while
    # creating integration files, or substitute a different app named "code".
    for relative in (*required, 'usr/bin', 'usr/share/icons/hicolor/1024x1024/apps',
                     'usr/share/icons/hicolor/1024x1024/apps/vscode.png', '.INSTALL'):
        path = root
        for part in Path(relative).parts:
            path /= part
            if path.is_symlink():
                raise RuntimeError('The VS Code package layout changed; unexpected symbolic link: '+relative)
    if any(not (root/name).is_file() for name in required):
        raise RuntimeError('The VS Code package layout changed; its Arch recipe must be reviewed.')
    try:
        product = json.loads((root/'usr/share/code/resources/app/product.json').read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError('Could not identify the VS Code package; its Arch recipe must be reviewed.') from error
    if not isinstance(product, dict) or product.get('applicationName') != 'code' or product.get('nameLong') != 'Visual Studio Code':
        raise RuntimeError('The package is not the supported Visual Studio Code Stable layout.')
    for name in ('usr/share/code/code', 'usr/share/code/bin/code'):
        if not (root/name).stat().st_mode & 0o111:
            raise RuntimeError('The VS Code package contains a non-executable launcher: '+name)
    # The vendor supplies this 1024px icon in pixmaps; hicolor makes it available
    # to the standard icon cache while retaining the original packaged file.
    original_icon = root/'usr/share/pixmaps/vscode.png'
    with original_icon.open('rb') as stream:
        header = stream.read(24)
    if header[:16] != b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' or header[16:24] != (1024).to_bytes(4, 'big') * 2:
        raise RuntimeError('The VS Code icon layout changed; its Arch recipe must be reviewed.')
    target = '../share/code/bin/code'
    if launcher.is_symlink():
        if launcher.readlink().as_posix() not in (target, '/usr/share/code/bin/code'):
            raise RuntimeError('The VS Code package contains an unexpected /usr/bin/code link.')
    elif launcher.exists():
        raise RuntimeError('The VS Code package contains an unexpected /usr/bin/code file.')
    else:
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.symlink_to(target)
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(original_icon, icon)
    icon.chmod(0o644)
    # The Debian scripts configure apt/debconf, update-alternatives, and a shared
    # optional /usr/bin/copilot alias. Keep the Copilot shim in the payload, but
    # leave that global command and editor preferences to the user. Pacman owns
    # the code launcher; its hooks handle caches, including upgrade and removal.
    (root/'.INSTALL').write_text('# VS Code uses package-owned launchers and native pacman desktop, icon and MIME hooks.\n')


def finalize(root, name):
    if name == CHROME:
        chrome_layout(root)
    elif name == VSCODE:
        vscode_layout(root)
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
