"""Exercise the X11 observer's import hook without a display or compositor."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('g++'), 'C++ compiler required')
class ImportHookTests(unittest.TestCase):
    def test_observes_only_main_executable_and_restores_relro_import(self):
        with tempfile.TemporaryDirectory(prefix='fusion-import-test-') as directory:
            root = Path(directory)
            (root/'library.cpp').write_text('''
extern "C" int fusion_test_event(int value) { return value + 1; }
extern "C" int fusion_library_call(int value) { return fusion_test_event(value); }
''')
            (root/'main.cpp').write_text('''
#include "import_hook_057.hpp"
#include <cassert>
#include <fstream>
#include <sstream>
#include <string>
extern "C" int fusion_test_event(int);
extern "C" int fusion_library_call(int);
int calls = 0;
auto original = fusion_test_event;
int observer(int value) { ++calls; return original(value); }
int writableMappings() {
    std::ifstream maps("/proc/self/maps");
    std::string line, address, permissions;
    int count = 0;
    while (std::getline(maps, line)) {
        std::istringstream fields(line); fields >> address >> permissions;
        if (permissions.size() > 1 && permissions[1] == 'w') ++count;
    }
    return count;
}
int main() {
    Wobbly::ImportHook hook;
    void* target = reinterpret_cast<void*>(original);
    void* replacement = reinterpret_cast<void*>(observer);
    assert(!hook.install("missing_symbol", target, replacement));
    assert(!hook.install("fusion_test_event", nullptr, replacement));
    assert(fusion_test_event(3) == 4);
    auto writable = writableMappings();
    assert(hook.install("fusion_test_event", target, replacement));
    assert(writableMappings() == writable);
    assert(fusion_test_event(3) == 4 && calls == 1);
    assert(fusion_library_call(5) == 6 && calls == 1);
    assert(!hook.install("fusion_test_event", target, replacement));
    assert(hook.remove());
    assert(writableMappings() == writable);
    assert(fusion_test_event(7) == 8 && calls == 1);
    assert(hook.remove());
}
''')
            subprocess.run(['g++','-O2','-shared','-fPIC',str(root/'library.cpp'),
                            '-o',str(root/'libfixture.so')],check=True)
            for calls in ('-fplt','-fno-plt'):
                with self.subTest(calls=calls):
                    subprocess.run(['g++','-std=c++23','-O2',calls,'-fPIE','-pie',
                                    '-Wl,-z,relro,-z,now',str(root/'main.cpp'),
                                    '-I'+str(ROOT/'config/hypr/effects/wobbly/native'),
                                    '-L'+str(root),'-Wl,-rpath,'+str(root),'-lfixture',
                                    '-o',str(root/'probe')],check=True)
                    subprocess.run([str(root/'probe')],check=True)
