"""New disk images and attachments are tested only in disposable directories."""

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from test_disk_removal import app, make_tab, emitted, assert_round_trip
import virtual_disk
from virtual_disk_dialog import VirtualDiskDialog


def wait_finished(dialog):
    for _ in range(300):
        if not dialog.running():
            return
        QTest.qWait(10)
    pytest.fail("Disk operation did not finish")


def test_sparse_image_has_exact_capacity_and_qemu_can_read_and_write_it(tmp_path):
    image = virtual_disk.create_image(tmp_path/'VM storage', 'Windows disk', 1)
    assert image.name == 'Windows disk.img'
    assert image.stat().st_size == virtual_disk.GIB
    assert image.stat().st_blocks * 512 < virtual_disk.GIB
    assert image.stat().st_mode & 0o777 == 0o600
    with image.open('rb') as stream:
        assert stream.read(4096) == bytes(4096)
        stream.seek(-4096, os.SEEK_END)
        assert stream.read() == bytes(4096)
    if shutil.which('qemu-img') and shutil.which('qemu-io'):
        info = json.loads(subprocess.check_output(['qemu-img', 'info', '--output=json', str(image)], text=True))
        assert info['format'] == 'raw' and info['virtual-size'] == virtual_disk.GIB
        subprocess.run(['qemu-io', '-f', 'file', '-c', 'write -P 0xa5 0 4096',
                        '-c', 'read -P 0xa5 0 4096', '-c', f'read -P 0 {virtual_disk.GIB-4096} 4096',
                        str(image)], check=True, capture_output=True, timeout=10)


@pytest.mark.parametrize('kind', ['file', 'directory', 'symlink', 'dangling-symlink'])
def test_existing_paths_are_never_overwritten(tmp_path, kind):
    image = tmp_path/'existing.img'
    target = tmp_path/'protected'
    target.write_bytes(b'existing guest data')
    if kind == 'file':
        image.write_bytes(b'existing image')
    elif kind == 'directory':
        image.mkdir()
    else:
        image.symlink_to(target if kind == 'symlink' else tmp_path/'missing')
    with pytest.raises(ValueError, match='already exists'):
        virtual_disk.create_image(tmp_path, image.name, 1)
    assert target.read_bytes() == b'existing guest data'
    if kind == 'file':
        assert image.read_bytes() == b'existing image'
    elif kind == 'directory':
        assert image.is_dir()
    else:
        assert image.is_symlink()


@pytest.mark.parametrize('name', ['', '..', '../guest.img', 'sub/guest.img', 'guest.qcow2', 'bad\0.img'])
def test_invalid_names_do_not_create_files(tmp_path, name):
    with pytest.raises(ValueError):
        virtual_disk.create_image(tmp_path, name, 1)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('size', [0, -1, True, 1.5, virtual_disk.MAX_GIB+1])
def test_invalid_capacity_does_not_create_files(tmp_path, size):
    with pytest.raises(ValueError):
        virtual_disk.create_image(tmp_path, 'guest.img', size)
    assert list(tmp_path.iterdir()) == []


def test_failed_creation_cleans_up_only_its_own_file(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError('No space left on device')
    monkeypatch.setattr(os, 'ftruncate', fail)
    with pytest.raises(OSError, match='No space'):
        virtual_disk.create_image(tmp_path, 'failed.img', 1)
    assert not (tmp_path/'failed.img').exists()


def test_destination_replacement_is_preserved_and_not_reported_as_created(tmp_path, monkeypatch):
    original = os.ftruncate
    def replace(fd, size):
        original(fd, size)
        image = tmp_path/'guest.img'
        image.unlink()
        image.write_bytes(b'new owner')
    monkeypatch.setattr(os, 'ftruncate', replace)
    with pytest.raises(RuntimeError, match='destination changed'):
        virtual_disk.create_image(tmp_path, 'guest.img', 1)
    assert (tmp_path/'guest.img').read_bytes() == b'new owner'


@pytest.mark.parametrize('profile', ['windows', 'macos'])
def test_create_button_attaches_image_without_changing_existing_disks(make_tab, tmp_path, profile):
    tab = make_tab(sata=['ide.0', 'ide.2'], profile=profile)
    before = copy.deepcopy(tab.cfg.data)
    changes = QSignalSpy(tab.changed)
    buttons = tab.lay.itemAt(1).layout()
    assert [buttons.itemAt(n).widget().text() for n in range(4)] == [
        'Add disk', 'Add ISO (CD-ROM)', 'Add NVMe controller', 'Add Virtual Disk']
    def fill():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, VirtualDiskDialog)
        dialog.location.setText(str(tmp_path))
        dialog.filename.setText('New guest.img')
        dialog.capacity.setValue(1)
        dialog.create.click()
    guard = QTimer()
    guard.setSingleShot(True)
    guard.timeout.connect(lambda: QApplication.activeModalWidget().reject() if QApplication.activeModalWidget() else None)
    guard.start(5000)
    QTimer.singleShot(0, fill)
    buttons.itemAt(3).widget().click()
    guard.stop()
    assert len(changes) == 1
    assert tab.cfg.blockdevs[:2] == before['blockdevs']
    assert tab.cfg.devices[:2] == before['devices']
    row = next(r for r in tab.rows if r.bd['filename'] == str(tmp_path/'New guest.img'))
    assert row.bd['driver'] == 'file' and row.bd['read-only'] is False
    assert row.bd['cache']['no-flush'] is False
    assert row.dev['bus'] == 'ide.1' and row.dev['driver'] == 'ide-hd'
    assert row.active.isChecked() and 'bootindex' not in row.dev
    assert tab.warn.toPlainText() == 'No disk problems found.'
    assert row.bd in emitted(tab.cfg, '-blockdev')
    assert row.dev in emitted(tab.cfg, '-device')
    row.cache.setCurrentText('none')
    row.regen_serial()
    assert row.bd['driver'] == 'file'
    assert_round_trip(tab.cfg, tmp_path)


def test_cancel_does_not_create_or_attach_anything(make_tab, tmp_path):
    tab = make_tab()
    before = copy.deepcopy(tab.cfg.data)
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
    tab.add_virtual_disk()
    assert tab.cfg.data == before
    assert list(tmp_path.iterdir()) == []


def test_full_sata_controller_stops_before_opening_creator(make_tab, monkeypatch):
    tab = make_tab(sata=[f'ide.{n}' for n in range(6)])
    before = copy.deepcopy(tab.cfg.data)
    messages = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: messages.append(args[-1]))
    tab.add_virtual_disk()
    assert messages and 'six SATA ports' in messages[0]
    assert tab.cfg.data == before


def test_creation_error_keeps_dialog_open_and_allows_retry(app, tmp_path):
    existing = tmp_path/'existing.img'
    existing.write_bytes(b'keep me')
    dialog = VirtualDiskDialog()
    dialog.location.setText(str(tmp_path))
    dialog.filename.setText(existing.name)
    dialog.capacity.setValue(1)
    dialog.show()
    dialog.create.click()
    wait_finished(dialog)
    assert dialog.isVisible() and dialog.selected_path is None
    assert dialog.create.isEnabled() and dialog.cancel.isEnabled()
    assert 'already exists' in dialog.status.text()
    assert existing.read_bytes() == b'keep me'
    dialog.filename.setText('retry.raw')
    dialog.create.click()
    wait_finished(dialog)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_path == tmp_path/'retry.raw'
    dialog.deleteLater()


def test_busy_creation_keeps_controls_locked_until_result(app, tmp_path, monkeypatch):
    release = threading.Event()
    original = virtual_disk.create_image
    def slow(*args):
        release.wait(3)
        return original(*args)
    monkeypatch.setattr(virtual_disk, 'create_image', slow)
    dialog = VirtualDiskDialog()
    dialog.location.setText(str(tmp_path))
    dialog.capacity.setValue(1)
    dialog.show()
    dialog.create.click()
    try:
        assert not dialog.fields.isEnabled() and not dialog.cancel.isEnabled()
        dialog.reject()
        assert dialog.isVisible()
    finally:
        release.set()
        wait_finished(dialog)
        dialog.deleteLater()
    assert dialog.selected_path == tmp_path/'virtual-disk.img'


def test_existing_image_is_read_without_changes(tmp_path):
    image = virtual_disk.create_image(tmp_path, 'Existing guest.raw', 1)
    with image.open('r+b') as stream:
        stream.write(b'existing guest contents')
        stream.seek(-4096, os.SEEK_END)
        stream.write(b'last sector data')
    before = image.stat()
    assert virtual_disk.existing_image(image) == image
    after = image.stat()
    assert (after.st_size, after.st_blocks, after.st_mtime_ns, after.st_mode) == (
        before.st_size, before.st_blocks, before.st_mtime_ns, before.st_mode)
    with image.open('rb') as stream:
        assert stream.read(23) == b'existing guest contents'
        stream.seek(-4096, os.SEEK_END)
        assert stream.read(16) == b'last sector data'


@pytest.mark.parametrize('kind', ['empty-path', 'relative', 'missing', 'folder', 'fifo', 'empty', 'partial-sector', 'iso'])
def test_invalid_existing_images_are_not_attached(tmp_path, kind):
    image = tmp_path/'guest.img'
    if kind == 'empty-path':
        image = ''
    elif kind == 'relative':
        image = 'relative.img'
    elif kind == 'folder':
        image.mkdir()
    elif kind == 'fifo':
        os.mkfifo(image)
    elif kind == 'empty':
        image.touch()
    elif kind == 'partial-sector':
        image.write_bytes(b'not a whole sector')
    elif kind == 'iso':
        image = tmp_path/'guest.iso'
        image.write_bytes(bytes(4096))
    with pytest.raises((ValueError, OSError)):
        virtual_disk.existing_image(image)


@pytest.mark.parametrize('link', ['same', 'symlink', 'hardlink'])
def test_existing_image_cannot_be_attached_twice(tmp_path, link):
    image = tmp_path/'guest.img'
    image.write_bytes(bytes(4096))
    alias = tmp_path/'alias.img'
    if link == 'symlink':
        alias.symlink_to(image)
    elif link == 'hardlink':
        os.link(image, alias)
    else:
        alias = image
    with pytest.raises(ValueError, match='already active'):
        virtual_disk.existing_image(alias, [str(tmp_path/'missing.img'), str(image)])
    assert image.read_bytes() == bytes(4096)


@pytest.mark.parametrize('format', ['qcow2', 'vmdk', 'vdi', 'vpc', 'vhdx'])
def test_renamed_container_image_is_rejected_without_qemu_dependency(tmp_path, monkeypatch, format):
    inspector = shutil.which('qemu-img')
    if not inspector:
        pytest.skip('qemu-img is needed to generate test container images')
    image = tmp_path/'misleading.img'
    subprocess.run([inspector, 'create', '-f', format, str(image), '4M'],
                   check=True, capture_output=True, timeout=10)
    before = image.stat()
    monkeypatch.setattr(shutil, 'which', lambda name: None)
    with pytest.raises(ValueError, match='not a raw'):
        virtual_disk.existing_image(image)
    after = image.stat()
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)


def test_raw_image_can_be_added_without_qemu_img(tmp_path, monkeypatch):
    image = tmp_path/'guest.img'
    image.write_bytes(bytes(4096))
    monkeypatch.setattr(shutil, 'which', lambda name: None)
    assert virtual_disk.existing_image(image) == image


@pytest.mark.parametrize('profile', ['windows', 'macos'])
def test_existing_disk_picker_attaches_without_recreating_image(make_tab, tmp_path, monkeypatch, profile):
    tab = make_tab(sata=['ide.0', 'ide.2'], profile=profile)
    image = tmp_path/'Saved guest.img'
    content = b'Guest data'.ljust(4096, b'\0')
    image.write_bytes(content)
    before = copy.deepcopy(tab.cfg.data)
    changes = QSignalSpy(tab.changed)
    selections = []
    def choose(*args):
        selections.append(args)
        return str(image), ''
    def must_not_create(*args):
        pytest.fail('Existing disks must never be recreated')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', choose)
    monkeypatch.setattr(virtual_disk, 'create_image', must_not_create)
    def fill():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, VirtualDiskDialog)
        dialog.mode.setCurrentIndex(1)
        assert dialog.new_fields.isHidden()
        assert dialog.create.text() == 'Add disk'
        dialog.browse_existing()
        dialog.create.click()
    QTimer.singleShot(0, fill)
    guard = QTimer()
    guard.setSingleShot(True)
    guard.timeout.connect(lambda: QApplication.activeModalWidget().reject() if QApplication.activeModalWidget() else None)
    guard.start(20000)
    tab.add_virtual_disk()
    guard.stop()
    assert len(changes) == 1 and len(selections) == 1
    assert image.read_bytes() == content
    assert tab.cfg.blockdevs[:2] == before['blockdevs']
    assert tab.cfg.devices[:2] == before['devices']
    row = next(r for r in tab.rows if r.bd.get('filename') == str(image))
    assert row.bd['driver'] == 'file' and not row.bd['read-only']
    assert row.dev['driver'] == 'ide-hd' and row.dev['bus'] == 'ide.1'
    assert tab.warn.toPlainText() == 'No disk problems found.'
    assert row.bd in emitted(tab.cfg, '-blockdev')
    assert_round_trip(tab.cfg, tmp_path)


def test_existing_file_error_offers_attach_with_same_path(app, tmp_path):
    image = tmp_path/'existing.img'
    content = b'Keep this guest'.ljust(4096, b'\0')
    image.write_bytes(content)
    dialog = VirtualDiskDialog()
    dialog.location.setText(str(tmp_path))
    dialog.filename.setText(image.name)
    dialog.show()
    dialog.create.click()
    wait_finished(dialog)
    assert 'Use existing' in dialog.status.text()
    dialog.mode.setCurrentIndex(1)
    assert dialog.existing_path.text() == str(image)
    dialog.create.click()
    wait_finished(dialog)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_path == image
    assert image.read_bytes() == content
    dialog.deleteLater()


def test_invalid_existing_disk_allows_retry_and_cancel(app, tmp_path):
    dialog = VirtualDiskDialog()
    dialog.mode.setCurrentIndex(1)
    dialog.existing_path.setText(str(tmp_path/'missing.img'))
    dialog.show()
    dialog.create.click()
    wait_finished(dialog)
    assert dialog.isVisible() and dialog.selected_path is None
    assert dialog.create.isEnabled() and dialog.fields.isEnabled() and dialog.cancel.isEnabled()
    assert 'Could not add' in dialog.status.text()
    dialog.mode.setCurrentIndex(0)
    assert not dialog.status.isVisible() and dialog.create.text() == 'Create and add'
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert list(tmp_path.iterdir()) == []
    dialog.deleteLater()
