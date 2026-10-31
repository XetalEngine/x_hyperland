#!/usr/bin/env python3
"""Build against the installed Qt private API, without a system installation."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parent


def system_includes(flags):
    """Keep vendor headers out of project-only warning checks, like CMake does."""
    result = []
    args = iter(flags)
    for flag in args:
        if flag == '-I':
            result += ['-isystem', next(args)]
        elif flag.startswith('-I'):
            result += ['-isystem', flag[2:]]
        else:
            result.append(flag)
    return result


def build_gtk():
    package = 'gtk+-3.0'
    version = subprocess.check_output(['pkg-config', '--modversion', package], text=True).strip()
    source = ROOT/'gtk_file_preview.c'
    destination = ROOT/'gtk3'; destination.mkdir(exist_ok=True)
    output = destination/'libxetal-file-preview.so'; stamp = destination/'version.txt'
    if (output.exists() and stamp.exists() and stamp.read_text().strip() == version
            and output.stat().st_mtime > max(source.stat().st_mtime, (ROOT/'gtk_file_places.h').stat().st_mtime)): return version
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', package, 'gio-unix-2.0', 'json-glib-1.0'], text=True))
    print('Theme: building GTK '+version+' file chooser integration.', flush=True)
    with tempfile.TemporaryDirectory(prefix='.build-', dir=ROOT) as temporary:
        subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-fPIC', '-shared',
                        str(source), '-o', temporary+'/preview.so', *flags], check=True)
        os.replace(temporary+'/preview.so', output)
    stamp.write_text(version+'\n')
    return version


def find_moc(major):
    candidates = []
    for variable in ('host_bins', 'libexecdir', 'bindir'):
        directory = subprocess.run(['pkg-config', '--variable='+variable, f'Qt{major}Core'], capture_output=True, text=True).stdout.strip()
        if directory: candidates.append(str(Path(directory)/'moc'))
    for program in (f'qtpaths{major}', f'qtpaths-qt{major}', f'qmake{major}', f'qmake-qt{major}'):
        if shutil.which(program):
            for key in ('QT_INSTALL_LIBEXECS', 'QT_INSTALL_BINS'):
                directory = subprocess.run([program, '--query' if 'qtpaths' in program else '-query', key], capture_output=True, text=True).stdout.strip()
                if directory: candidates.append(str(Path(directory)/'moc'))
    candidates += [f'/usr/lib/qt{major}/moc',f'/usr/lib/qt{major}/libexec/moc',f'/usr/lib64/qt{major}/libexec/moc']
    candidates += [value for name in (f'moc-qt{major}', f'moc{major}', 'moc') if (value := shutil.which(name))]
    for candidate in dict.fromkeys(candidates):
        if not Path(candidate).is_file(): continue
        result = subprocess.run([candidate,'-v'],capture_output=True,text=True)
        if result.returncode == 0 and f'moc {major}.' in result.stdout+result.stderr: return candidate
    raise RuntimeError(f'Qt {major} moc was not found. Install Qt {major} development tools.')


def build():
    versions = {'gtk3': build_gtk()}
    for major in (5, 6):
        moc = find_moc(major)
        package = f'Qt{major}Widgets'
        version = subprocess.check_output(['pkg-config', '--modversion', package], text=True).strip()
        headers = Path(subprocess.check_output(['pkg-config', '--variable=includedir', package], text=True).strip())
        destination = ROOT/f'qt{major}/platformthemes'; destination.mkdir(parents=True, exist_ok=True)
        output = destination/'libxetaltheme.so'
        stamp = destination/'version.txt'
        sources = [ROOT/'platformtheme.cpp', ROOT/'plugin.json', ROOT/'file_preview.hpp', ROOT/'file_places.hpp', Path(__file__)]
        if (output.exists() and stamp.exists() and stamp.read_text().strip() == version
                and output.stat().st_mtime > max(p.stat().st_mtime for p in sources)):
            versions[str(major)] = version; continue
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', package, f'Qt{major}Concurrent'], text=True))
        print(f'Theme: building Qt {version} integration; moc: {moc}; headers: {headers}', flush=True)
        private = []
        for module in ['QtGui', 'QtCore']:
            private += ['-I'+str(headers/module/version), '-I'+str(headers/module/version/module)]
        with tempfile.TemporaryDirectory(prefix='.build-', dir=ROOT) as temporary:
            includes = [flag for flag in flags if flag.startswith(('-I', '-D'))]
            subprocess.run([moc, *includes, *private, str(ROOT/'platformtheme.cpp'), '-o', temporary+'/platformtheme.moc'], check=True)
            # GCC 16 diagnoses Qt 6.10's incomplete-type SFINAE in its own
            # headers. Keep -Werror on our sources, with Qt's public/private
            # headers correctly classified as system headers for the compiler.
            subprocess.run(['c++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-fPIC', '-shared',
                            '-I'+temporary, *system_includes(private), str(ROOT/'platformtheme.cpp'),
                            '-o', temporary+'/plugin.so', *system_includes(flags)], check=True)
            os.replace(temporary+'/plugin.so', output)
        stamp.write_text(version+'\n'); versions[str(major)] = version
    return versions


if __name__ == '__main__': print(json.dumps(build()))
