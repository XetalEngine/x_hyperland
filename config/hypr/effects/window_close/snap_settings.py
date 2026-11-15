"""KDE-only layout snapping. Kept separate from per-window decoration rules."""
import fcntl
import hashlib
import json
from pathlib import Path
from PyQt6.QtWidgets import QGroupBox,QVBoxLayout,QHBoxLayout,QLabel,QCheckBox,QPushButton
from . import controller

PATH=Path(__file__).with_name('snap-settings.json')

def load(path=PATH):
    raw=path.read_bytes() if path.exists() else b''
    if len(raw)>1024:raise ValueError('Snap settings are too large.')
    data=json.loads(raw) if raw else {'enabled':True}
    if not isinstance(data,dict) or set(data)!={'enabled'} or type(data['enabled']) is not bool:raise ValueError('Invalid snap settings.')
    return data['enabled'],hashlib.sha256(raw).hexdigest()

def save(enabled,token,path=PATH):
    if type(enabled) is not bool:raise ValueError('Invalid snap setting.')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if load(path)[1]!=token:raise ValueError('Snap settings changed elsewhere. Reload before applying.')
        old=path.read_bytes() if path.exists() else None
        controller.atomic(path,(json.dumps({'enabled':enabled})+'\n').encode())
        try:controller.hypr('dispatch','xetalwindowclose:reload')
        except Exception:
            if old is None:path.unlink(missing_ok=True)
            else:controller.atomic(path,old)
            try:controller.hypr('dispatch','xetalwindowclose:reload')
            except Exception:pass
            raise
    return load(path)

class SnapSettings(QGroupBox):
    def __init__(self,parent=None):
        super().__init__('Snap layouts · all KDE workspaces',parent)
        layout=QVBoxLayout(self);self.enabled=QCheckBox('Enable snap layouts');layout.addWidget(self.enabled)
        hint=QLabel('Drag to a side for halves or a corner for quarters. At the top edge, choose a layout for halves, quarters or thirds. '
                    'Pause briefly over a layout, then release. Drag away to restore the previous size. Esc cancels snapping.')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        for text,callback in [('Reload',self.load),('Apply snap settings',self.apply)]:
            button=QPushButton(text);button.clicked.connect(callback);buttons.addWidget(button)
        self.load()
    def load(self):
        try:
            enabled,self.token=load();self.enabled.setChecked(enabled);self.status.clear()
        except (OSError,ValueError) as error:self.token=None;self.status.setText(str(error))
    def apply(self):
        try:
            _,self.token=save(self.enabled.isChecked(),self.token)
            status=json.loads(controller.hypr('xetal-windowclose'))
            self.status.setText('Applied to KDE workspaces.' if status.get('snap_layouts_supported') else
                                'Saved. Log out and back in to load the new native snap layouts.')
        except Exception as error:self.status.setText(str(error))
