"""Configure an app launch shortcut through Control desk's validated binding store."""
from __future__ import annotations
import copy
import subprocess
from PyQt6.QtCore import Qt,QObject,QRunnable,QThreadPool,QTimer,pyqtSignal
from PyQt6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QPushButton,QLineEdit,QComboBox,QCheckBox,QMessageBox)
import hotkeys
from key_capture import CaptureEdit
from editor import DIALOG_STYLE,image_icon
import shortcuts


class ApplySignals(QObject):
    finished=pyqtSignal(object)
    failed=pyqtSignal(str)


class ApplyJob(QRunnable):
    def __init__(self,store,records,expected):
        super().__init__();self.store=store;self.records=records;self.expected=expected;self.signals=ApplySignals()
    def run(self):
        try:self.signals.finished.emit(self.store.apply(self.records,self.expected))
        except Exception as exc:self.signals.failed.emit(str(exc))


def compositor(*args):
    result=subprocess.run(['hyprctl',*args],capture_output=True,text=True,timeout=2)
    if result.returncode:raise RuntimeError((result.stderr or result.stdout or 'Could not contact Hyprland.').strip())
    return result.stdout.strip()


class HotkeyDialog(QDialog):
    def __init__(self,entry,parent=None,store=None,adapter=None):
        super().__init__(parent)
        self.adapter=adapter or hotkeys
        self.entry=entry;self.store=store or hotkeys.keys.Store();self.records=[];self.expected='';self.values={}
        self.busy=False;self.loading=False;self.job=None;self.saved=False
        self.setWindowTitle('Launch hotkey · '+entry.get_display_name());self.resize(590,490)
        self.setMinimumWidth(500)
        self.setStyleSheet(shortcuts.theme_runtime.stylesheet(DIALOG_STYLE+'''
QComboBox { background: #0d1622; color: #e2edf9; border: 1px solid #344b62; border-radius: 7px; padding: 10px; }
QComboBox QAbstractItemView { background: #14202f; selection-background-color: #315768; }
QLabel#hotkeyPreview { color: #80e2d8; background: #182b38; border: 1px solid #315768; border-radius: 10px; font-size: 23px; font-weight: 600; padding: 17px; }
QPushButton:disabled { color: #71859b; background: #202b39; }
'''))
        layout=QVBoxLayout(self);layout.setContentsMargins(24,22,24,22);layout.setSpacing(14)
        heading=QHBoxLayout();icon=QLabel();icon.setPixmap(image_icon(entry.fields['icon']).pixmap(48,48));heading.addWidget(icon)
        titles=QVBoxLayout();name=QLabel(entry.get_display_name());name.setTextFormat(Qt.TextFormat.PlainText)
        name.setObjectName('dialogTitle');name.setWordWrap(True);titles.addWidget(name)
        hint=QLabel('Launch this app from any workspace.');hint.setObjectName('muted');titles.addWidget(hint)
        heading.addLayout(titles,1);layout.addLayout(heading)
        self.choice=QComboBox();self.choice.setAccessibleName('Configured launch hotkey');layout.addWidget(self.choice)
        self.preview=QLabel('Choose a shortcut');self.preview.setObjectName('hotkeyPreview')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.preview)
        self.record=QPushButton('Record shortcut…');self.record.clicked.connect(self.begin_capture);layout.addWidget(self.record)
        form=QFormLayout();form.setVerticalSpacing(10)
        self.mods=QLineEdit();self.mods.setPlaceholderText('SUPER CTRL SHIFT ALT')
        self.key=CaptureEdit();self.key.setPlaceholderText('For example: K, F8, Return')
        form.addRow('Modifiers',self.mods);form.addRow('Key',self.key);layout.addLayout(form)
        self.enabled=QCheckBox('Enable this hotkey');layout.addWidget(self.enabled)
        hint=QLabel('Also shown in Control desk → Hotkeys → Applications.\nUse Super to keep ordinary typing shortcuts available to apps.')
        hint.setObjectName('muted');hint.setWordWrap(True);layout.addWidget(hint)
        self.message=QLabel();self.message.setObjectName('error');self.message.setWordWrap(True);layout.addWidget(self.message)
        layout.addStretch()
        bottom=QHBoxLayout();self.reload_button=QPushButton('Reload');self.reload_button.clicked.connect(self.reload);bottom.addWidget(self.reload_button)
        self.remove=QPushButton('Remove hotkey…');self.remove.clicked.connect(self.remove_hotkey);bottom.addWidget(self.remove)
        bottom.addStretch();self.cancel=QPushButton('Cancel');self.cancel.clicked.connect(self.reject);bottom.addWidget(self.cancel)
        self.apply_button=QPushButton('Apply hotkey');self.apply_button.setObjectName('primary')
        self.apply_button.clicked.connect(self.apply);bottom.addWidget(self.apply_button);layout.addLayout(bottom)
        self.choice.currentIndexChanged.connect(self.select_binding)
        self.mods.textChanged.connect(self.validate);self.key.textChanged.connect(self.validate);self.enabled.toggled.connect(self.validate)
        self.key.captured.connect(self.captured);self.key.cancelled.connect(self.stop_capture)
        self.capture_timer=QTimer(self);self.capture_timer.setSingleShot(True);self.capture_timer.setInterval(10000)
        self.capture_timer.timeout.connect(self.stop_capture)
        self.capture_poll=QTimer(self);self.capture_poll.setInterval(250);self.capture_poll.timeout.connect(self.poll_capture)
        self.reload()

    def reload(self):
        if self.busy:return
        self.stop_capture();self.loading=True
        try:
            self.records,self.expected=self.store.load();self.values=hotkeys.keys.variables(self.store.main.read_text())
            bindings=self.adapter.matches(self.entry,self.records,self.values)
            self.choice.clear()
            for b in bindings:
                suffix=' · disabled' if not b.enabled else ''
                self.choice.addItem(hotkeys.display(b,self.values)+suffix,b.id)
            self.choice.addItem('Add another hotkey…' if bindings else 'New launch hotkey',None)
            self.choice.setCurrentIndex(0);self.message.clear()
        except Exception as exc:
            self.expected='';self.message.setText(str(exc))
        self.loading=False;self.select_binding()

    def selected(self):return next((b for b in self.records if b.id==self.choice.currentData()),None)

    def select_binding(self,*_):
        if self.loading:return
        self.stop_capture();self.loading=True;b=self.selected()
        self.mods.setText(hotkeys.keys.expand(b.mods,self.values) if b else 'SUPER')
        self.key.setText(b.key if b else '');self.enabled.setChecked(b.enabled if b else True)
        allowed=not (b and b.protected)
        for widget in (self.mods,self.key,self.enabled,self.record):widget.setEnabled(allowed)
        self.remove.setEnabled(bool(b) and allowed);self.loading=False;self.validate()

    def candidate(self,remove=False):
        return self.adapter.edited(self.records,self.entry,self.choice.currentData(),self.mods.text(),self.key.text(),self.enabled.isChecked(),remove)

    def validate(self,*_):
        if self.loading or self.busy:return
        text='Choose a shortcut'
        if self.key.text().strip():
            b=hotkeys.keys.Binding('','','Applications',True,self.mods.text(),self.key.text(),'exec')
            text=hotkeys.display(b,self.values)
        self.preview.setText(text)
        if not self.expected:self.apply_button.setEnabled(False);return
        try:
            records=self.candidate();hotkeys.keys.validate_fields(records);hotkeys.keys.protect_typing(records,self.values)
            errors=hotkeys.keys.conflicts(records,self.values)
            if errors:raise hotkeys.keys.ConfigError('\n'.join(errors))
            self.apply_button.setEnabled(not self.key.recording)
            self.message.clear()
        except Exception as exc:
            self.apply_button.setEnabled(False)
            self.message.setText(str(exc) if self.key.text().strip() else '')

    def apply(self):
        if self.busy:return
        self.validate()
        if self.apply_button.isEnabled():self.save(self.candidate())

    def remove_hotkey(self):
        b=self.selected()
        if not b or b.protected or self.busy:return
        self.stop_capture()
        prompt=QMessageBox(self);prompt.setWindowTitle('Remove launch hotkey?');prompt.setTextFormat(Qt.TextFormat.PlainText)
        prompt.setText('Remove '+hotkeys.display(b,self.values)+' for '+self.entry.get_display_name()+'?')
        prompt.setInformativeText(getattr(self.adapter,'remove_message','The app and its favorite stay in your menu. This removes only this launch hotkey.'))
        remove=prompt.addButton('Remove hotkey',QMessageBox.ButtonRole.DestructiveRole)
        cancel=prompt.addButton(QMessageBox.StandardButton.Cancel);prompt.setDefaultButton(cancel);prompt.setEscapeButton(cancel)
        prompt.exec()
        if prompt.clickedButton()==remove:self.save(self.candidate(remove=True))

    def save(self,records):
        self.stop_capture();self.busy=True;self.setEnabled(False)
        self.message.setText('Validating and applying your hotkey…')
        self.job=ApplyJob(self.store,copy.deepcopy(records),self.expected)
        self.job.signals.finished.connect(self.applied);self.job.signals.failed.connect(self.failed)
        QThreadPool.globalInstance().start(self.job)

    def applied(self,result):
        self.busy=False;self.setEnabled(True);self.saved=True;self.accept()

    def failed(self,message):
        self.busy=False;self.setEnabled(True);self.message.setText(message)

    def begin_capture(self):
        if self.busy or self.key.recording:return
        try:
            if compositor('submap') not in ('','reset','default'):
                raise RuntimeError('Another shortcut mode is active. Finish or cancel it before recording here.')
            response=compositor('dispatch','submap',hotkeys.keys.CAPTURE_MAP)
            if response!='ok':raise RuntimeError(response)
        except Exception as exc:self.message.setText(str(exc));return
        self.key.recording=True;self.key.setFocus();self.capture_timer.start();self.capture_poll.start()
        self.record.setText('Listening…');self.apply_button.setEnabled(False)
        self.message.setText('Press your shortcut. Escape cancels; recording ends after 10 seconds.')

    def captured(self,mods,key):
        self.stop_capture();self.loading=True;self.mods.setText(mods);self.key.setText(key);self.loading=False;self.validate()

    def poll_capture(self):
        try:
            if compositor('submap')!=hotkeys.keys.CAPTURE_MAP:self.stop_capture()
        except Exception:self.stop_capture()

    def stop_capture(self,*_):
        if not self.key.recording:return
        self.key.recording=False;self.capture_timer.stop();self.capture_poll.stop();self.record.setText('Record shortcut…')
        try:
            if compositor('submap')==hotkeys.keys.CAPTURE_MAP:compositor('dispatch','submap','reset')
        except Exception:pass
        self.validate()

    def reject(self):
        if self.busy:return
        self.stop_capture();super().reject()

    def closeEvent(self,event):
        if self.busy:event.ignore();return
        self.stop_capture();super().closeEvent(event)

    def hideEvent(self,event):
        self.stop_capture();super().hideEvent(event)
