"""Exercise real child output without installing packages or touching a profile."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'installer'))
import install
from wizard import failure_message


class BuildDiagnosticsTests(unittest.TestCase):
    def test_compiler_error_survives_long_output_and_recovery(self):
        child = """import sys
print('Compiling theme', flush=True)
print('preview.cpp:12: fatal error: missing-header.h: No such file', file=sys.stderr, flush=True)
for i in range(700): print('compiler context '+str(i), flush=True)
print('Traceback: outer build command failed', file=sys.stderr)
sys.exit(1)
"""
        progress = io.StringIO()
        with redirect_stdout(progress), self.assertRaises(RuntimeError) as failure:
            install.run_build([sys.executable, '-c', child], 'theme/build.py')
        self.assertIn('Compiling theme', progress.getvalue())
        self.assertIn('compiler context 699', progress.getvalue())
        message = str(failure.exception)
        self.assertIn('missing-header.h', message.splitlines()[0])
        self.assertLessEqual(len(message.splitlines()), 62)
        self.assertNotIn('compiler context 0\n', message)
        after_recovery = ['Previous Fedora runtime restored.',
                          'Installation stopped: '+message]
        visible = failure_message('\n'.join(after_recovery).splitlines())
        self.assertIn('theme/build.py', visible)
        self.assertIn('missing-header.h', visible)
        self.assertNotIn('Traceback', visible)

    def test_progress_is_streamed_before_child_exits(self):
        with tempfile.TemporaryDirectory(prefix='xetal-build-output-') as temporary:
            ready = Path(temporary)/'ready'
            class Progress(io.StringIO):
                def write(self, value):
                    if 'waiting for progress reader' in value:
                        ready.touch()
                    return super().write(value)
            child = f"""import pathlib, time, sys
ready = pathlib.Path({str(ready)!r})
print('waiting for progress reader', flush=True)
deadline = time.monotonic()+5
while not ready.exists() and time.monotonic()<deadline: time.sleep(.01)
sys.exit(0 if ready.exists() else 2)
"""
            with redirect_stdout(Progress()):
                install.run_build([sys.executable, '-c', child], 'test build')

    def test_silent_failure_is_identified(self):
        with self.assertRaisesRegex(RuntimeError, r'Build failed: theme/build.py \(exit 7\)'):
            install.run_build([sys.executable, '-c', 'raise SystemExit(7)'], 'theme/build.py')

    def test_non_build_errors_and_cancellation_keep_their_message(self):
        self.assertEqual(failure_message(['earlier output', 'Setup cancelled.', '']), 'Setup cancelled.')
        self.assertEqual(failure_message([]), 'Setup stopped. See installation details.')


if __name__ == '__main__':
    unittest.main()
