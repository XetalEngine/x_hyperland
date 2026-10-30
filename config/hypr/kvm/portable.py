"""Private runtime paths and clean first-run profiles for the built-in KVM app."""
from pathlib import Path
import json
import os
import shutil

ROOT = Path(__file__).resolve().parent


def data_root():
    return Path(os.environ.get('XETAL_KVM_DATA', str(Path.home()/'.local/share/xetal-kvm'))).absolute()


def component_path(name):
    return data_root()/'components'/name/'current'


def tool_defaults():
    return configuration('windows')['tools']


def configuration(profile):
    """Resolve the captured profile's paths for this installation."""
    if profile not in ('windows', 'macos'):
        raise ValueError('Unknown profile')
    data = json.loads((ROOT/'defaults'/(profile+'.json')).read_text())
    def resolve(value):
        if isinstance(value, dict): return {k:resolve(v) for k,v in value.items()}
        if isinstance(value, list): return [resolve(v) for v in value]
        if isinstance(value, str):
            return value.replace('${KVM_DATA}', str(data_root())).replace('${KVM_APP}', str(ROOT))
        return value
    return resolve(data)


def seed_assets():
    """Each guest owns its writable copy; updates never replace edited assets."""
    assets = ROOT/'defaults/assets'
    for source in assets.rglob('*'):
        if source.is_file():
            _copy_new(source, data_root()/source.relative_to(assets))


def _copy_new(source, target):
    if not source.is_file() or target.exists(): return
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Link the complete temporary copy into place, without replacing any file
    # created concurrently. An interrupted first run never leaves a partial ROM.
    import tempfile
    fd, temporary = tempfile.mkstemp(prefix='.'+target.name, dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as output, source.open('rb') as stream:
            shutil.copyfileobj(stream, output)
            output.flush(); os.fsync(output.fileno())
        try: os.link(temporary, target)
        except FileExistsError: pass
    finally:
        os.unlink(temporary)


def prepare():
    root = data_root()
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    seed_assets()
    for profile in ('windows','macos'):
        directory = root if profile=='windows' else root/'macos'
        for child in ('presets','run','firmware'):
            (directory/child).mkdir(parents=True,exist_ok=True,mode=0o700)
        filename = 'win10-template.json' if profile=='windows' else 'macos-template.json'
        template = directory/'presets'/filename
        if not template.exists():
            _write_new(template,configuration(profile))
        _write_new(directory/'settings_default.json',json.loads(template.read_text()))
        _write_new(directory/'presets/smbios-default.json',configuration(profile)['smbios'])
        _write_new(directory/'settings_default.theme.json',dict(accent='',background='',text='',preset=0))
    prepare_firmware()


def _write_new(path,value):
    try:
        with path.open('x') as stream:
            json.dump(value,stream,indent=2); stream.write('\n')
        path.chmod(0o600)
    except FileExistsError:
        pass


def prepare_firmware():
    """Keep private NVRAM and OpenCore copies separate from package updates."""
    seed_assets()
    source = component_path('ovmf')/'OVMF_VARS.fd'
    for directory in (data_root(), data_root()/'macos'):
        _copy_new(source, directory/'firmware/OVMF_VARS.fd')
    _copy_new(component_path('opencore')/'boot/OpenCore.img',
              data_root()/'macos/boot/OpenCore.img')


def prepare_tpm_workspace():
    """Install runtime helpers only, leaving local identities and edits intact."""
    source = component_path('tpm')
    target = data_root()/'tpm-workspace'
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    for path in (source/'scripts').rglob('*'):
        if path.is_file():
            destination = target/path.relative_to(source)
            existed = destination.exists()
            _copy_new(path, destination)
            if not existed and destination.exists(): destination.chmod(path.stat().st_mode & 0o777)
    install = target/'_install'
    if not install.exists() and source.is_dir(): install.symlink_to(source, target_is_directory=True)
