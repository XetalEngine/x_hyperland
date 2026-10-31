"""Compile vendor-header regressions without changing installed Qt or the profile."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('theme_build', ROOT/'config/hypr/theme/build.py')
theme_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(theme_build)


@unittest.skipUnless(shutil.which('c++'), 'C++ compiler is required')
class ThemeHeaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='xetal-theme-headers-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.vendor = self.root/'vendor headers'
        self.vendor.mkdir()
        self.source = self.root/'theme.cpp'
        self.source.write_text('#include <dependency.hpp>\nint main() {}\n')

    def compile(self, includes):
        return subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                               '-fsyntax-only', *includes, str(self.source)],
                              capture_output=True, text=True)

    def test_gcc16_vendor_sfinae_warning_does_not_abort_build(self):
        probe = subprocess.run(['c++', '-Werror', '-Wsfinae-incomplete', '-x', 'c++', '-fsyntax-only', '-'],
                               input='', capture_output=True, text=True)
        if probe.returncode:
            self.skipTest('Compiler does not have the GCC 16 SFINAE warning')
        # Same incomplete-type substitution pattern as Qt 6.10's public headers.
        (self.vendor/'dependency.hpp').write_text('''#include <iterator>
#include <type_traits>
#include <utility>
class Later;
template<class T, class = void> struct HasData : std::false_type {};
template<class T> struct HasData<T, std::void_t<decltype(std::data(std::declval<T &>()))>> : std::true_type {};
static_assert(!HasData<Later>::value);
class Later { public: int *data(); };
''')
        previous = self.compile(['-I'+str(self.vendor)])
        self.assertNotEqual(previous.returncode, 0)
        self.assertIn('sfinae-incomplete', previous.stderr)
        for includes in (['-I'+str(self.vendor)], ['-I', str(self.vendor)]):
            result = self.compile(theme_build.system_includes(includes))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_project_warnings_are_still_errors(self):
        (self.vendor/'dependency.hpp').write_text('struct VendorType {};\n')
        self.source.write_text('#include <dependency.hpp>\nint main() { int unused; }\n')
        result = self.compile(theme_build.system_includes(['-I'+str(self.vendor)]))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unused', result.stderr)

    def test_invalid_vendor_header_is_still_an_error(self):
        (self.vendor/'dependency.hpp').write_text('struct VendorType { MissingType member; };\n')
        result = self.compile(theme_build.system_includes(['-I'+str(self.vendor)]))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('MissingType', result.stderr)


if __name__ == '__main__':
    unittest.main()
