"""History rotation uses disposable logs, never host services or real VM state."""
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import launcher
import virtual_gpu


@pytest.fixture
def history(tmp_path, monkeypatch):
    path = tmp_path / 'run' / 'launch.log'
    monkeypatch.setattr(launcher, 'LOG', str(path))
    monkeypatch.setattr(virtual_gpu, 'service_active', lambda: False)
    return path


def test_clear_read_only_history_without_privileges(history):
    history.parent.mkdir()
    history.write_text('completed run\n')
    history.chmod(0o444)
    original = history.stat().st_ino
    other = history.parent / 'other-profile.log'
    other.write_text('keep this\n')
    assert launcher.clear_log() == str(history)
    assert history.read_text() == ''
    assert history.stat().st_ino != original
    assert history.stat().st_uid == os.getuid()
    assert history.stat().st_mode & 0o777 == 0o600
    assert other.read_text() == 'keep this\n'
    assert not list(history.parent.glob('.launch-log-*'))


def test_clear_missing_history_creates_empty_log(history):
    launcher.clear_log()
    assert history.is_file() and history.read_bytes() == b''


def test_clear_failure_preserves_history_and_removes_temporary_file(history, monkeypatch):
    history.parent.mkdir()
    history.write_text('completed run\n')
    def refuse(*_):
        raise PermissionError('fixture: replacement denied')
    monkeypatch.setattr(launcher.os, 'replace', refuse)
    with pytest.raises(PermissionError, match='replacement denied'):
        launcher.clear_log()
    assert history.read_text() == 'completed run\n'
    assert not list(history.parent.glob('.launch-log-*'))


def test_running_vm_keeps_its_open_log(history, monkeypatch):
    history.parent.mkdir()
    history.write_text('VM STARTED\n')
    original = history.stat().st_ino
    monkeypatch.setattr(virtual_gpu, 'service_active', lambda: True)
    with pytest.raises(RuntimeError, match='Shut down'):
        launcher.clear_log()
    assert history.stat().st_ino == original
    assert history.read_text() == 'VM STARTED\n'


def test_clear_replaces_symlink_without_truncating_its_target(history):
    history.parent.mkdir()
    target = history.parent / 'unrelated.txt'
    target.write_text('preserve\n')
    history.symlink_to(target)
    launcher.clear_log()
    assert target.read_text() == 'preserve\n'
    assert not history.is_symlink()
    assert history.read_bytes() == b''
