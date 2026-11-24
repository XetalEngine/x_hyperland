"""Window behavior controls inside Theme → Window effects."""
import json
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QCheckBox,QPushButton
from . import behavior,controller


class WindowBehaviorPage(QWidget):
    def __init__(self,async_run):
        super().__init__();self.async_run=async_run;self.dirty=self.busy=False;self.token=None;self.baseline=True
        layout=QVBoxLayout(self);layout.setContentsMargins(16,16,16,16)
        title=QLabel('Keep your windows within reach');title.setObjectName('brand');layout.addWidget(title)
        self.protection=QCheckBox('Protect title bars from going off screen or behind the taskbar')
        self.protection.setAccessibleName('Title-bar protection');self.protection.toggled.connect(self.changed);layout.addWidget(self.protection)
        hint=QLabel('Enabled by default. After you finish dragging, an obscured title bar moves smoothly back into the usable area of its monitor. '
                    'Window size and workspace stay the same. Fullscreen apps and snap layouts keep their normal behavior.')
        hint.setWordWrap(True);hint.setObjectName('muted');layout.addWidget(hint)
        layout.addStretch()
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();layout.addLayout(row)
        self.defaults=QPushButton('Restore default');self.defaults.clicked.connect(lambda:self.protection.setChecked(True));row.addWidget(self.defaults);row.addStretch()
        self.reload=QPushButton('Reload');self.reload.clicked.connect(lambda:self.refresh(True));row.addWidget(self.reload)
        self.discard=QPushButton('Discard');self.discard.clicked.connect(lambda:self.protection.setChecked(self.baseline));row.addWidget(self.discard)
        self.apply=QPushButton('Apply behavior');self.apply.setObjectName('primary');self.apply.clicked.connect(self.save);row.addWidget(self.apply)
        self.refresh()

    def changed(self):
        self.dirty=self.protection.isChecked()!=self.baseline
        for control in (self.protection,self.defaults,self.reload):control.setEnabled(not self.busy)
        self.apply.setEnabled(self.token is not None and self.dirty and not self.busy)
        self.discard.setEnabled(self.dirty and not self.busy)

    def refresh(self,force=False):
        if self.busy or (self.dirty and not force):return
        try:
            self.baseline,self.token=behavior.load();self.protection.setChecked(self.baseline)
            self.status.setText('Title-bar protection is on.' if self.baseline else 'Title-bar protection is off. Super + left drag can recover an obscured window.')
        except (OSError,ValueError) as error:self.token=None;self.status.setText(str(error))
        self.changed()

    def save(self):
        if self.busy or not self.dirty or self.token is None:return
        self.busy=True;self.changed();enabled=self.protection.isChecked();token=self.token
        def work():
            value=behavior.save(enabled,token)
            try:active=json.loads(controller.hypr('xetal-windowclose')).get('titlebar_protection_supported',False)
            except (OSError,ValueError,RuntimeError):active=False
            return value,active
        def done(result):
            (self.baseline,self.token),active=result;self.busy=False;self.changed()
            self.status.setText('Window behavior saved.' if active else 'Saved. Sign out and back in to load the updated window behavior.')
        def failed(message):self.busy=False;self.changed();self.status.setText(str(message))
        self.async_run(work,done,failed)
