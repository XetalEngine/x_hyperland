"""Compiler probes and repair dispatch, without installing host packages."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'installer'))
import dependencies
import install
import native_toolchain


class ToolchainTests(unittest.TestCase):
    def test_driver_version_alone_does_not_pass_missing_backend(self):
        with tempfile.TemporaryDirectory() as name:
            compiler=Path(name)/'g++'
            compiler.write_text('#!/bin/sh\nif [ "$1" = --version ]; then echo GCC-16; exit; fi\n'
                                'echo "cannot execute cc1plus: No such file or directory" >&2\nexit 1\n')
            compiler.chmod(0o700)
            self.assertEqual(subprocess.run([str(compiler),'--version'],capture_output=True).returncode,0)
            with patch.object(native_toolchain,'compiler',return_value=str(compiler)):
                self.assertIn('cc1plus',native_toolchain.problem())

    def test_foreign_compiler_paths_do_not_leak_into_native_effects(self):
        with patch.dict(os.environ,{'GCC_EXEC_PREFIX':'/broken/sdk/','COMPILER_PATH':'/broken/sdk','PATH':'/broken/sdk/bin'}):
            env=native_toolchain.environment()
            self.assertNotIn('GCC_EXEC_PREFIX',env);self.assertNotIn('COMPILER_PATH',env)
            self.assertTrue(env['PATH'].startswith('/usr/bin:/bin:'))
            self.assertEqual(native_toolchain.compiler(),'/usr/bin/g++')

    def test_repair_uses_each_distributions_compiler_packages_and_verifies_result(self):
        for family,manager,backend in [('arch','pacman','gcc'),('fedora','dnf','gcc-c++'),('debian','apt-get','g++-14')]:
            with self.subTest(family=family),patch.object(dependencies,'distro',return_value=family), \
                 patch.object(native_toolchain,'problem',side_effect=['missing cc1plus','']), \
                 patch.object(dependencies.runtime_install,'administrator',return_value=['sudo']), \
                 patch.object(dependencies.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'g++-14 ii\nlibstdc++-14-dev ii\n','')) as run:
                dependencies.repair_toolchain(yes=True)
                command=run.call_args.args[0]
                self.assertEqual(command[:2],['sudo',manager]);self.assertIn(backend,command)
                self.assertNotIn('--needed',command)

    def test_working_compiler_never_requests_reinstall(self):
        with patch.object(native_toolchain,'problem',return_value=''),patch.object(dependencies.subprocess,'run') as run:
            dependencies.repair_toolchain(yes=True)
            run.assert_not_called()

    def test_window_controls_must_build_before_setup_succeeds(self):
        def run(args,**kwargs):
            broken=str(args[-1]).endswith('/effects/window_close/build.py')
            return subprocess.CompletedProcess(args,1 if broken else 0,'','missing cc1plus' if broken else '')
        with patch.object(install,'run_build'),patch.object(install.subprocess,'run',side_effect=run):
            with self.assertRaisesRegex(RuntimeError,'Window controls.*forced workspace layout'):
                install.build(Path('/fixture'))


if __name__=='__main__':unittest.main()
