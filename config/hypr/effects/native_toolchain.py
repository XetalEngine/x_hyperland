"""Use the distribution C++ toolchain, including its matching compiler backend."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ADAPTERS = {
    'efb50993780079460b0cbed1363e2166a2de1d9f': 'plugin.cpp',
    '11cbc6c577b84ffb1edf4df3fc5b6128c3ae6947': 'plugin_057.cpp',
}


def adapter(directory, commit):
    """Select only a source adapter written for these exact compositor headers."""
    name = ADAPTERS.get(commit)
    source = Path(directory)/name if name else None
    if source is None or not source.is_file():
        raise RuntimeError('No Hyper Fusion native adapter for these Hyprland headers.')
    return source


def adapter_headers(hypr_root):
    return sorted((Path(hypr_root)/'runtime').glob('*_057.hpp'))


def compiler():
    # A desktop started by an AppImage/SDK can inherit a different g++ wrapper.
    # Its cc1plus often is not shipped. Build plugins against the host toolchain.
    system = Path('/usr/bin/g++')
    return str(system) if system.is_file() else (shutil.which('g++') or 'g++')


def environment():
    env = dict(os.environ)
    for name in ('GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH', 'CPATH',
                 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH'):
        env.pop(name, None)
    env['PATH'] = '/usr/bin:/bin:' + env.get('PATH', os.defpath)
    return env


def problem():
    """Compile and link C++23: a driver/version query cannot detect lost cc1plus."""
    source = '#include <string>\n#include <vector>\nint main(){std::vector<std::string> v{"ready"};return v.size()!=1;}\n'
    try:
        with tempfile.TemporaryDirectory(prefix='fusion-compiler-check-') as directory:
            result = subprocess.run([compiler(), '-std=c++23', '-x', 'c++', '-', '-o', str(Path(directory)/'check')],
                                    input=source, capture_output=True, text=True, timeout=30, env=environment())
            if result.returncode:
                return (result.stderr or result.stdout).strip()[-3000:]
    except (OSError, subprocess.TimeoutExpired) as error:
        return str(error)
    return ''
