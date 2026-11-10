#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Rebuild the pinned engine entirely offline. No system 7-Zip is used."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent


def replace(path, before, after):
    text = path.read_text()
    if text.count(before) != 1:
        raise RuntimeError(f'Pinned source does not match the adapter: {path.name}: {before[:70]}')
    path.write_text(text.replace(before, after))


def patch(source):
    console = source/'CPP/7zip/UI/Console'
    shutil.copyfile(ROOT/'native/FusionEvents.h', console/'FusionEvents.h')
    enumeration = source/'CPP/7zip/UI/Common/EnumDirItems.cpp'
    replace(enumeration, '#include "StdAfx.h"', '#include "StdAfx.h"\n#include "../Console/FusionEvents.h"')
    text = enumeration.read_text()
    if text.count('CanIncludeItem(fi.IsDir())') != 4:
        raise RuntimeError('Pinned source socket-filter insertion points changed')
    enumeration.write_text(text.replace('CanIncludeItem(fi.IsDir())',
        'CanIncludeItem(fi.IsDir()) && !FusionEvents::isSocket(fi.GetPosixAttrib())'))
    for name in ('List.cpp', 'PercentPrinter.cpp', 'UpdateCallbackConsole.cpp',
                 'ExtractCallbackConsole.cpp', 'UserInputUtils.cpp'):
        path = console/name
        replace(path, '#include "StdAfx.h"', '#include "StdAfx.h"\n#include "FusionEvents.h"')
    replace(console/'PercentPrinter.cpp', 'void CPercentPrinter::Print()\n{',
            'void CPercentPrinter::Print()\n{\n  FusionEvents::progress(Total, Completed, Files, FileName, Command);\n'
            '  if (FusionEvents::descriptor() >= 0) return;')
    replace(console/'PercentPrinter.cpp', 'void CPercentPrinter::ClosePrint(bool needFlush)\n{',
            'void CPercentPrinter::ClosePrint(bool needFlush)\n{\n'
            '  if (FusionEvents::descriptor() >= 0) { FusionEvents::progress(Total, Completed, Files, FileName, Command, true); return; }')
    replace(console/'UserInputUtils.cpp', 'static bool GetPassword(CStdOutStream *outStream, UString &psw)\n{',
            'static bool GetPassword(CStdOutStream *outStream, UString &psw)\n{\n'
            '  if (FusionEvents::descriptor() >= 0) return FusionEvents::password(psw);')
    for method, stage in (('ScanError_Base', 'scan'), ('OpenFileError_Base', 'open'), ('ReadingFileError_Base', 'read')):
        signature = f'HRESULT CCallbackConsoleBase::{method}(const FString &path, DWORD systemError)\n{{'
        replace(console/'UpdateCallbackConsole.cpp', signature,
                signature + f'\n  FusionEvents::error(fs2us(path), systemError, "{stage}");')
    replace(console/'ExtractCallbackConsole.cpp',
            'Z7_COM7F_IMF(CExtractCallbackConsole::SetOperationResult(Int32 opRes, Int32 encrypted))\n{',
            'Z7_COM7F_IMF(CExtractCallbackConsole::SetOperationResult(Int32 opRes, Int32 encrypted))\n{\n'
            '  if (opRes != 0) FusionEvents::error(_currentName, (unsigned)opRes, "extract");')
    replace(console/'List.cpp', '      RINOK(fp.PrintItemInfo(i, st))', '''      if (FusionEvents::descriptor() >= 0) {
        std::string record = "\\"event\\":\\"entry\\",\\"path\\":" + FusionEvents::quote(fp.FilePath)
          + ",\\"directory\\":" + (fp.IsDir ? "true" : "false")
          + ",\\"size\\":" + std::to_string(st.Size.Def ? st.Size.Val : 0)
          + ",\\"packed\\":" + std::to_string(st.PackSize.Def ? st.PackSize.Val : 0);
        const PROPID ids[] = { kpidSymLink, kpidHardLink, kpidMethod, kpidEncrypted, kpidPosixAttrib };
        const char *keys[] = { "symlink", "hardlink", "method", "encrypted", "mode" };
        for (unsigned j = 0; j < 5; ++j) {
          CPropVariant prop;
          RINOK(archive->GetProperty(i, ids[j], &prop))
          record += ",\\""; record += keys[j]; record += "\\":";
          if (prop.vt == VT_BSTR) record += FusionEvents::quote(prop.bstrVal);
          else if (prop.vt == VT_BOOL) record += prop.boolVal ? "true" : "false";
          else if (prop.vt == VT_UI4) record += std::to_string(prop.ulVal);
          else record += "null";
        }
        FusionEvents::send(record);
      }
      else { RINOK(fp.PrintItemInfo(i, st)) }''')


def build():
    metadata = json.loads((ROOT/'vendor/manifest.json').read_text())
    archive = ROOT/'vendor'/metadata['source']['file']
    if hashlib.sha256(archive.read_bytes()).hexdigest() != metadata['source']['sha256']:
        raise RuntimeError('Bundled 7-Zip source checksum mismatch')
    with tempfile.TemporaryDirectory(prefix='fusion-7zip-build-') as temporary:
        source = Path(temporary)
        with tarfile.open(archive) as bundle: bundle.extractall(source, filter='data')
        patch(source)
        jobs = os.environ.get('CMAKE_BUILD_PARALLEL_LEVEL') or str(min(8, os.cpu_count() or 1))
        subprocess.run(['make', '-f', 'makefile.gcc', '-j'+jobs,
                        'LDFLAGS_STATIC_2=-static-libstdc++ -static-libgcc',
                        'CXXFLAGS_EXTRA=-Wno-error=array-bounds'],
                       cwd=source/'CPP/7zip/Bundles/Alone2', check=True)
        binary = source/'CPP/7zip/Bundles/Alone2/_o/7zz'
        if not binary.is_file():
            matches = list((source/'CPP/7zip/Bundles/Alone2').rglob('7zz'))
            if len(matches) != 1: raise RuntimeError('Build did not produce one engine')
            binary = matches[0]
        destination = ROOT/'vendor/7zz-fusion'
        shutil.copyfile(binary, destination); destination.chmod(0o755)
        metadata['engine']['sha256'] = hashlib.sha256(destination.read_bytes()).hexdigest()
        metadata['engine']['linking'] = 'Bundled GCC C++ runtime; system glibc'
        metadata['engine']['compiler'] = subprocess.check_output(['g++','-dumpfullversion'],text=True).strip()
        versions = re.findall(r'Name: GLIBC_([0-9.]+)', subprocess.check_output(
            ['readelf','--version-info',str(destination)],text=True))
        metadata['engine']['minimum_glibc'] = max(versions,key=lambda v:tuple(map(int,v.split('.'))))
        (ROOT/'vendor/manifest.json').write_text(json.dumps(metadata, indent=2)+'\n')
    return destination


if __name__ == '__main__': print(build())
