"""Small, explicit Arch adaptations; never execute Debian maintainer scripts.

Chrome's native layout follows the maintained google-chrome AUR recipe:
https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=google-chrome
"""
import argparse
import grp
import json
from pathlib import Path
import pwd
import shlex
import shutil
import stat
import subprocess
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from deb_dependencies import parse_relationships

CHROME = 'google-chrome-stable'
CHROME_EXTRAS = ('libxss', 'libxtst', 'hicolor-icon-theme', 'desktop-file-utils')
CHROME_CRON = ('etc/cron.daily/google-chrome', 'opt/google/chrome/cron/google-chrome')
VSCODE = 'code'
VSCODE_EXTRAS = ('desktop-file-utils', 'gtk-update-icon-cache', 'hicolor-icon-theme', 'shared-mime-info')
OPERA = 'opera-stable'
ONEPASSWORD = '1password'
ANYDESK = 'anydesk'
DESKTOP_HOOKS = ('desktop-file-utils', 'gtk-update-icon-cache', 'hicolor-icon-theme', 'shared-mime-info')
NATIVE_EXTRAS = {
    OPERA: (*DESKTOP_HOOKS, 'gtk3', 'libxss', 'libnotify'),
    ONEPASSWORD: (*DESKTOP_HOOKS, 'python', 'shadow', 'polkit'),
    # AnyDesk 8.1.0 links libevdev.so.2 without declaring it in its control file.
    ANYDESK: (*DESKTOP_HOOKS, 'polkit', 'lsb-release', 'libevdev'),
}
RECIPE_NOTICES = {
    OPERA: 'Opera: native desktop hooks and sandbox permissions replace Debian APT/debconf setup.',
    ONEPASSWORD: '1Password: package-owned launchers, Polkit policy and protected integration helpers replace Debian setup.',
    ANYDESK: 'AnyDesk: package-owned systemd service and native hooks replace Debian service setup. Unattended access stays opt-in.',
}


def without_setup_groups(text, names):
    """Omit only whole, recognized setup-only groups for a reviewed recipe."""
    kept = []
    for raw, group in zip(text.split(','), parse_relationships(text)):
        if (all(req.name in names and req.qualifier is None and req.operator in (None, '>=')
                for req in group)):
            continue
        kept.append(raw.strip())
    return ', '.join(kept)


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
    elif fields['package'] in NATIVE_EXTRAS:
        if fields['package'] == OPERA:
            # These configure the Debian repository/prompt, not browser runtime.
            # Unknown alternative members or architecture constraints stay checked.
            for key, names in (('pre-depends', {'apt-transport-https'}),
                               ('depends', {'debconf', 'debconf-2.0'})):
                value = without_setup_groups(result.get(key, ''), names)
                if value:
                    result[key] = value
                else:
                    result.pop(key, None)
        result['depends'] = ', '.join(filter(None, [result.get('depends', ''), *NATIVE_EXTRAS[fields['package']]]))
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


def recipe_path(root, relative, *, leaf_link=False):
    """Known recipe paths must never write through a payload symlink."""
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or '..' in parts:
        raise RuntimeError('Invalid recipe path: ' + relative)
    path = root
    for index, part in enumerate(parts):
        path /= part
        if path.is_symlink() and not (leaf_link and index == len(parts)-1):
            raise RuntimeError('The package layout changed; unexpected symbolic link: ' + relative)
    return path


def require_file(root, relative, *, executable=False):
    path = recipe_path(root, relative)
    if not path.is_file():
        raise RuntimeError('The package layout changed; missing regular file: ' + relative)
    if executable:
        with path.open('rb') as stream:
            magic = stream.read(4)
        if magic != b'\x7fELF' or not path.stat().st_mode & 0o111:
            raise RuntimeError('The package layout changed; expected executable ELF: ' + relative)
    return path


def install_content(root, relative, content, mode=0o644):
    path = recipe_path(root, relative)
    if path.exists() and (not path.is_file() or path.read_bytes() != content):
        raise RuntimeError('The package layout changed; unexpected existing file: ' + relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(mode)
    return path


def install_link(root, relative, target):
    path = recipe_path(root, relative, leaf_link=True)
    if path.is_symlink():
        if path.readlink().as_posix() != target:
            raise RuntimeError('The package layout changed; unexpected launcher: ' + relative)
    elif path.exists():
        raise RuntimeError('The package layout changed; unexpected launcher file: ' + relative)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)


def add_metadata(root, key, value):
    path = require_file(root, '.PKGINFO')
    text = path.read_text()
    # Never add a self-conflict if Debtap changes its naming convention.
    if key in ('conflict', 'provides') and f'pkgname = {value}\n' in text:
        return
    line = f'{key} = {value}\n'
    if line not in text.splitlines(keepends=True):
        path.write_text(text.rstrip('\n')+'\n'+line)


def native_hooks(root, description, script=''):
    path = recipe_path(root, '.INSTALL')
    path.write_text('# '+description+'\n'+script)
    path.chmod(0o644)


def opera_layout(root):
    # Keep the vendor's private directory and its existing relative launcher.
    # Debtap does not relocate Debian multiarch subdirectories.
    app = 'usr/lib/x86_64-linux-gnu/opera-stable'
    require_file(root, app+'/opera', executable=True)
    sandbox = require_file(root, app+'/opera_sandbox', executable=True)
    desktop = require_file(root, 'usr/share/applications/opera.desktop').read_text()
    if 'Name=Opera\n' not in desktop or 'Exec=opera %U\n' not in desktop:
        raise RuntimeError('The Opera desktop layout changed; review its Arch recipe.')
    install_link(root, 'usr/bin/opera', '../lib/x86_64-linux-gnu/opera-stable/opera')
    if stat.S_IMODE(sandbox.stat().st_mode) not in (0o755, 0o4755):
        raise RuntimeError('Unexpected Opera sandbox permissions; review its Arch recipe.')
    sandbox.chmod(0o4755)  # The vendor postinst and native Arch recipe require this.
    add_metadata(root, 'conflict', 'opera')
    native_hooks(root, 'Opera uses native desktop/icon/MIME hooks. APT and default-browser alternatives are not configured.')


# Self-contained, package-owned native integration helper. It does not execute
# vendor shell/template code. Owners come from the installation target's users,
# not the machine that built/exported the converted package.
ONEPASSWORD_SETUP = '''#!/usr/bin/env python3
import grp
import os
from pathlib import Path
import pwd
import stat
import subprocess
from xml.sax.saxutils import escape

if os.geteuid() != 0:
    raise SystemExit('1Password integration setup requires root')

def owned_file(name):
    path = Path(name)
    if path.resolve(strict=True) != path:
        raise RuntimeError('Unexpected symlink in 1Password integration: ' + name)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if info.st_uid != 0 or not stat.S_ISREG(info.st_mode):
        os.close(fd)
        raise RuntimeError('Expected root-owned 1Password file: ' + name)
    return fd

for group, binary in (('onepassword', '1Password-BrowserSupport'),
                      ('onepassword-mcp', '1password-mcp')):
    try:
        entry = grp.getgrnam(group)
    except KeyError:
        subprocess.run(['groupadd', '--system', group], check=True)
        entry = grp.getgrnam(group)
    fd = owned_file('/opt/1Password/' + binary)
    try:
        os.fchown(fd, 0, entry.gr_gid)
        os.fchmod(fd, 0o2755)
    finally:
        os.close(fd)

template = '/opt/1Password/com.1password.1Password.policy.tpl'
fd = owned_file(template)
with os.fdopen(fd) as stream:
    text = stream.read()
if text.count('${POLICY_OWNERS}') != 2:
    raise RuntimeError('1Password policy template changed')
owners = ' '.join('unix-user:' + user.pw_name for user in pwd.getpwall()
                  if 1000 <= user.pw_uid <= 9999).split()[:10]
policy = text.replace('${POLICY_OWNERS}', escape(' '.join(owners))).encode()
target = '/usr/share/polkit-1/actions/com.1password.1Password.policy'
fd = owned_file(target)
os.close(fd)
fd = os.open(target, os.O_WRONLY | os.O_NOFOLLOW)
try:
    info = os.fstat(fd)
    if info.st_uid != 0 or not stat.S_ISREG(info.st_mode):
        raise RuntimeError('Unexpected 1Password policy file')
    os.ftruncate(fd, 0)
    with os.fdopen(fd, 'wb', closefd=False) as stream:
        stream.write(policy)
        stream.flush()
    os.fchmod(fd, 0o644)
    os.fsync(fd)
finally:
    os.close(fd)
'''


def onepassword_layout(root):
    app = 'opt/1Password/'
    for name in ('1password', '1Password-BrowserSupport', '1password-mcp', 'chrome-sandbox'):
        require_file(root, app+name, executable=True)
    require_file(root, 'usr/share/applications/com.onepassword.OnePassword.desktop')
    template = require_file(root, app+'com.1password.1Password.policy.tpl').read_text()
    if template.count('${POLICY_OWNERS}') != 2:
        raise RuntimeError('The 1Password policy template changed; review its Arch recipe.')
    try:
        actions = {node.get('id') for node in ET.fromstring(template).findall('action')}
    except ET.ParseError as error:
        raise RuntimeError('The 1Password policy template is invalid; review its Arch recipe.') from error
    if actions != {'com.1password.1Password.unlock', 'com.1password.1Password.authorizeCLI',
                   'com.1password.1Password.authorizeSshAgent'}:
        raise RuntimeError('The 1Password policy actions changed; review its Arch recipe.')
    browsers = require_file(root, app+'resources/custom_allowed_browsers').read_bytes()
    sandbox = require_file(root, app+'chrome-sandbox')
    if stat.S_IMODE(sandbox.stat().st_mode) not in (0o755, 0o4755):
        raise RuntimeError('Unexpected 1Password sandbox permissions; review its Arch recipe.')
    sandbox.chmod(0o4755)
    install_link(root, 'usr/bin/1password', '/opt/1Password/1password')
    install_link(root, 'usr/bin/1password-mcp', '/opt/1Password/1password-mcp')
    install_link(root, app+'onepassword-mcp', '/opt/1Password/1password-mcp')
    install_content(root, 'usr/share/doc/1password/examples/custom_allowed_browsers', browsers)
    install_content(root, 'etc/1password/custom_allowed_browsers', browsers)
    install_content(root, 'usr/share/polkit-1/actions/com.1password.1Password.policy',
                    template.replace('${POLICY_OWNERS}', 'unix-user:root').encode())
    install_content(root, 'usr/lib/hyperfusion-deb/1password-setup.py', ONEPASSWORD_SETUP.encode())
    add_metadata(root, 'backup', 'etc/1password/custom_allowed_browsers')
    for conflict in ('1password-beta', '1password-beta-bin'):
        add_metadata(root, 'conflict', conflict)
    native_hooks(root, '1Password uses native protected helpers, Polkit and desktop hooks; no APT/debsig changes.', '''post_install() {
    python /usr/lib/hyperfusion-deb/1password-setup.py
}
post_upgrade() { post_install; }
''')


def anydesk_layout(root):
    require_file(root, 'usr/bin/anydesk', executable=True)
    require_file(root, 'usr/share/applications/anydesk.desktop')
    require_file(root, 'usr/share/polkit-1/actions/com.anydesk.anydesk.policy')
    service = require_file(root, 'usr/share/anydesk/files/systemd/anydesk.service').read_bytes()
    if b'ExecStart=/usr/bin/anydesk --service\n' not in service or b'User=root\n' not in service:
        raise RuntimeError('The AnyDesk service layout changed; review its Arch recipe.')
    install_content(root, 'usr/lib/systemd/system/anydesk.service', service)
    add_metadata(root, 'conflict', 'anydesk-bin')
    native_hooks(root, 'AnyDesk service is package-owned; unattended access is opt-in, as in the native AUR package.', '''post_install() {
    printf '%s\\n' 'AnyDesk unattended access is optional: sudo systemctl enable --now anydesk.service'
}
post_upgrade() {
    if [ -d /run/systemd/system ]; then
        systemctl daemon-reload
        systemctl try-restart anydesk.service
    fi
}
pre_remove() {
    if [ -d /run/systemd/system ]; then
        systemctl stop anydesk.service
    fi
}
''')


def permission_changes(name):
    # Explicit native equivalents of the vendors' postinst chmod operations.
    # No other file, permission widening, or private source mode is accepted.
    path = {OPERA: 'usr/lib/x86_64-linux-gnu/opera-stable/opera_sandbox',
            ONEPASSWORD: 'opt/1Password/chrome-sandbox'}.get(name)
    return {path: (0o755, 0o4755)} if path else {}


def verify_installed_recipe(name, root=Path('/')):
    for relative, (_, mode) in permission_changes(name).items():
        info = require_file(root, relative).stat()
        if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != mode:
            raise RuntimeError('Native sandbox permissions were not installed correctly: /'+relative)
    if name == ONEPASSWORD:
        for group, binary in (('onepassword', '1Password-BrowserSupport'), ('onepassword-mcp', '1password-mcp')):
            info = require_file(root, 'opt/1Password/'+binary).stat()
            try:
                gid = grp.getgrnam(group).gr_gid
            except KeyError as error:
                raise RuntimeError('1Password integration group was not created: '+group) from error
            if info.st_uid != 0 or info.st_gid != gid or stat.S_IMODE(info.st_mode) != 0o2755:
                raise RuntimeError('1Password integration permissions were not configured: '+binary)
        policy = require_file(root, 'usr/share/polkit-1/actions/com.1password.1Password.policy').read_text()
        template = require_file(root, 'opt/1Password/com.1password.1Password.policy.tpl').read_text()
        owners = ['unix-user:'+user.pw_name for user in pwd.getpwall() if 1000 <= user.pw_uid <= 9999][:10]
        if template.count('${POLICY_OWNERS}') != 2 or policy != template.replace('${POLICY_OWNERS}', escape(' '.join(owners))):
            raise RuntimeError('1Password native Polkit setup did not finish')


def finalize(root, name):
    if name == CHROME:
        chrome_layout(root)
    elif name == VSCODE:
        vscode_layout(root)
    elif name == OPERA:
        opera_layout(root)
    elif name == ONEPASSWORD:
        onepassword_layout(root)
    elif name == ANYDESK:
        anydesk_layout(root)
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
