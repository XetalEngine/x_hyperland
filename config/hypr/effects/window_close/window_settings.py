#!/usr/bin/env python3
"""A small, themed editor opened by the Super-only window gear."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'theme'))
from effects.window_close import model, rules, controller
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
                            QSpinBox,QFormLayout,QPushButton,QDialogButtonBox,QWidget)


class Preview(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.rule=dict(rules.DEFAULTS);self.setMinimumHeight(118)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette=self.palette();area=QRectF(8,8,self.width()-16,self.height()-16)
        p.setPen(QPen(palette.mid().color(),1));p.setBrush(palette.base());p.drawRoundedRect(area,9,9)
        p.setPen(palette.text().color());p.drawText(area,Qt.AlignmentFlag.AlignCenter,'Your window')
        size=18+(self.rule['size']-24)*.16;gap=5;width=size*4+gap*3
        anchor=self.rule['anchor'];x=area.right()-width-10 if anchor.endswith('right') else (area.center().x()-width/2 if anchor.endswith('center') else area.left()+10)
        y=area.bottom()-size-10 if anchor.startswith('bottom') else area.top()+10
        for n,glyph in enumerate(('⚙','−','□','×')):
            box=QRectF(x+n*(size+gap),y,size,size)
            p.setBrush(palette.button());p.setPen(QPen(palette.highlight().color(),1));p.drawRoundedRect(box,4,4)
            p.setPen(palette.buttonText().color());p.drawText(box,Qt.AlignmentFlag.AlignCenter,glyph)


class RuleDialog(QDialog):
    def __init__(self,window_id,parent=None):
        super().__init__(parent)
        self.window_id=str(window_id);self.info=controller.window_info(self.window_id)
        self.setWindowTitle('Window controls');self.setMinimumWidth(480);self.resize(560,610)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,20,24,20);layout.setSpacing(14)
        title=QLabel('Window controls, your way');title.setStyleSheet('font-size: 21px; font-weight: 700;');layout.addWidget(title)
        app=QLabel(self.info['app'] or 'This window');app.setTextFormat(Qt.TextFormat.PlainText)
        app.setWordWrap(True);layout.addWidget(app)
        form=QFormLayout();form.setSpacing(10)
        self.scope=QComboBox();self.scope.addItem('Only this window · until it closes','window')
        if self.info['app']:self.scope.addItem('All windows of this app · remembered','app')
        form.addRow('Apply to',self.scope)
        self.mode=QComboBox()
        for key,label in rules.MODES.items():self.mode.addItem(label,key)
        form.addRow('Show controls',self.mode)
        self.size=QSpinBox();self.size.setRange(24,64);self.size.setSuffix(' px');form.addRow('Button size',self.size)
        self.anchor=QComboBox()
        for key,label in rules.ANCHORS.items():self.anchor.addItem(label,key)
        form.addRow('Position',self.anchor)
        offsets=QWidget();row=QHBoxLayout(offsets);row.setContentsMargins(0,0,0,0)
        self.x=QSpinBox();self.y=QSpinBox()
        for label,control in [('Across',self.x),('Down / up',self.y)]:
            control.setRange(0,4000);control.setSuffix(' px');row.addWidget(QLabel(label));row.addWidget(control)
        form.addRow('Distance from edge',offsets)
        self.proximity=QSpinBox();self.proximity.setRange(12,400);self.proximity.setSuffix(' px')
        form.addRow('Nearby distance',self.proximity);layout.addLayout(form)
        self.preview=Preview();layout.addWidget(self.preview)
        hint=QLabel('The gear appears only while Super is held, even when controls are Off. '
                    'Buttons stay inside the visible window and hide during dragging and the final wobble.')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        footer=QHBoxLayout();self.inherit=QPushButton('Use inherited settings');self.inherit.clicked.connect(lambda:self.apply(True));footer.addWidget(self.inherit)
        self.reload=QPushButton('Reload');self.reload.clicked.connect(self.load);footer.addWidget(self.reload);footer.addStretch()
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Close)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setObjectName('primary')
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(lambda:self.apply())
        self.buttons.rejected.connect(self.reject);footer.addWidget(self.buttons);layout.addLayout(footer)
        self.scope.currentIndexChanged.connect(self.load)
        for control in (self.mode,self.anchor):control.currentIndexChanged.connect(self.preview_values)
        for control in (self.size,self.x,self.y,self.proximity):control.valueChanged.connect(self.preview_values)
        self.load()

    def values(self):
        return dict(mode=self.mode.currentData(),size=self.size.value(),anchor=self.anchor.currentData(),
                    x=self.x.value(),y=self.y.value(),proximity=self.proximity.value())

    def preview_values(self,*_):
        self.proximity.setEnabled(self.mode.currentData()=='nearby')
        self.preview.rule=self.values();self.preview.update()

    def load(self,*_):
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(False)
        self.inherit.setEnabled(False)
        try:
            self.info=controller.window_info(self.window_id)
            scope=self.scope.currentData();path,section=controller.rule_file(scope)
            data,self.token=rules.load(path,section);key=self.info['app'] if scope=='app' else self.window_id
            self.saved=data[section].get(key)
            settings,_=model.load();apps,_=rules.load()
            inherited=apps['apps'].get(self.info['app']) if scope=='window' else None
            value=rules.effective(settings,inherited,self.saved)
            self.mode.setCurrentIndex(self.mode.findData(value['mode']));self.anchor.setCurrentIndex(self.anchor.findData(value['anchor']))
            for key in ('size','x','y','proximity'):getattr(self,key).setValue(value[key])
            self.inherit.setEnabled(self.saved is not None)
            self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(True)
            self.status.setText('This window has its own override. The app choice also applies to its other windows.' if scope=='app' and self.info['window_override'] else
                                'Using your choice.' if self.saved else 'Following the app choice.' if inherited else 'Following the global window button settings.')
            self.preview_values()
        except Exception as error:self.status.setText(str(error))

    def apply(self,inherit=False):
        try:
            controller.save_rule(self.window_id,self.scope.currentData(),None if inherit else self.values(),self.token)
            self.load()
            if self.scope.currentData()=='app' and self.info['window_override']:
                self.status.setText('Saved for this app. This window still has its own override; choose Only this window → Use inherited settings to follow the app.')
            else:self.status.setText('Applied. '+('Saved for future windows and logins.' if self.scope.currentData()=='app' else 'This choice lasts until this window closes.'))
        except Exception as error:self.status.setText(str(error))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--window-id',required=True);args=parser.parse_args()
    import runtime as theme_runtime
    os.environ.update(theme_runtime.environment())
    app=QApplication(sys.argv[:1]);app.setDesktopFileName('fusion-window-buttons')
    theme_runtime.install(app,'QLabel { background: transparent; } QDialog { padding: 0; } QPushButton { padding: 7px 10px; }')
    try:
        session=controller.instance_dir();dialog=RuleDialog(args.window_id)
    except Exception as error:
        print(str(error),file=sys.stderr);return 1
    # This helper belongs only to the session that opened it.
    timer=QTimer(app);timer.setInterval(1500);timer.timeout.connect(lambda:app.quit() if not (session/'.socket.sock').exists() else None);timer.start()
    dialog.show();return app.exec()


if __name__=='__main__':sys.exit(main())
