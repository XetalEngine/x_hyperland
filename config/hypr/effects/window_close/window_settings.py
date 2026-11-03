#!/usr/bin/env python3
"""A themed editor with temporary previews on the actual target window."""
import argparse
import os
from pathlib import Path
import secrets
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'theme'))
from effects.window_close import model, rules, controller
from effects.window_close.drag_page import DragSettings
from PyQt6.QtCore import Qt, QTimer, QProcess, QObject, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
                            QSpinBox,QSlider,QFormLayout,QPushButton,QDialogButtonBox,QWidget,
                            QColorDialog,QScrollArea,QFrame)


class DesktopPicker(QObject):
    """Wayland-native eyedropper; no clipboard or persistent screenshot files."""
    picked=pyqtSignal(QColor)
    finished=pyqtSignal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.process=QProcess(self);self.stage='';self.cancelled=False
        self.process.finished.connect(self.complete)
        self.process.errorOccurred.connect(self.error)
        self.timeout=QTimer(self);self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.cancel)

    def start(self):
        self.cancelled=False
        if shutil.which('hyprpicker'):
            # --quiet also suppresses the selected color in some hyprpicker
            # releases. Accept only a complete hex-color line from its output.
            self.stage='color';self.process.start('hyprpicker',['--format','hex','--no-fancy'])
        elif shutil.which('slurp') and shutil.which('grim'):
            self.stage='point';self.process.start('slurp',['-p'])
        else:
            self.finished.emit('Screen picking needs hyprpicker, or slurp and grim. You can still choose a color here.');return
        self.timeout.start(120000)

    def error(self,error):
        if error==QProcess.ProcessError.FailedToStart:
            self.timeout.stop();self.finished.emit('Could not start the screen picker: '+self.process.errorString())

    def complete(self,code,*_):
        output=bytes(self.process.readAllStandardOutput())
        self.process.readAllStandardError()
        if self.cancelled:return
        if code!=0:
            self.timeout.stop();self.finished.emit('Screen picking cancelled. Your color is unchanged.');return
        if self.stage=='point':
            # A point request returns only geometry, passed as one argument.
            import re
            geometry=output.decode(errors='replace').strip()
            if not re.fullmatch(r'-?\d+,-?\d+ 1x1',geometry):
                self.timeout.stop();self.finished.emit('The screen picker did not return a pixel.');return
            self.stage='pixel';self.process.start('grim',['-g',geometry,'-s','1','-t','png','-'])
            self.timeout.start(10000);return
        self.timeout.stop()
        color=QColor()
        if self.stage=='color':
            import re
            text=output.decode(errors='replace').strip()
            colors=re.findall(r'^#[0-9a-fA-F]{6}$',text,re.MULTILINE)
            if len(colors)==1:color=QColor(colors[0])
        elif self.stage=='pixel' and len(output)<65536:
            image=QImage.fromData(output)
            if not image.isNull() and image.width()==1 and image.height()==1:color=image.pixelColor(0,0)
        if color.isValid():
            color.setAlpha(255);self.picked.emit(color);self.finished.emit('Color previewed on your window. Apply to save it.')
        else:self.finished.emit('Could not read the selected color. Your color is unchanged.')

    def cancel(self):
        self.cancelled=True;self.timeout.stop()
        if self.process.state()!=QProcess.ProcessState.NotRunning:
            self.process.kill();self.process.waitForFinished(500)
        self.finished.emit('Screen picking cancelled. Your color is unchanged.')


class SliderControl(QWidget):
    valueChanged=pyqtSignal(int)

    def __init__(self,low,high,parent=None):
        super().__init__(parent)
        row=QHBoxLayout(self);row.setContentsMargins(0,0,0,0);row.setSpacing(12)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.setRange(low,high)
        self.spin=QSpinBox();self.spin.setRange(low,high);self.spin.setSuffix(' px')
        self.spin.setKeyboardTracking(False);self.spin.setMinimumWidth(88)
        row.addWidget(self.slider,1);row.addWidget(self.spin)
        self.limit=high
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self._changed)

    def _changed(self,value):
        self.slider.setMaximum(max(self.limit,value));self.slider.setValue(value)
        self.valueChanged.emit(value)

    def setSliderMaximum(self,value):
        self.limit=max(self.spin.minimum(),min(self.spin.maximum(),int(value)))
        self.slider.setMaximum(max(self.limit,self.value()))

    def setValue(self,value):self.spin.setValue(value)
    def value(self):return self.spin.value()


class RuleDialog(QDialog):
    def __init__(self,window_id,parent=None):
        super().__init__(parent)
        self.window_id=str(window_id);self.info=controller.window_info(self.window_id)
        self.preview_token=secrets.token_hex(16);self.closing=False;self.loading=True
        self.preview_dirty=False;self.valid=False;self.remove_override=False
        self.color_dialog=None;self.background_color=rules.DEFAULTS['background_color'];self.picking=False
        self.setWindowTitle('Window controls');self.setMinimumWidth(540);self.resize(640,790)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,20,24,20);layout.setSpacing(14)
        title=QLabel('Window controls, your way');title.setStyleSheet('font-size: 21px; font-weight: 700;');layout.addWidget(title)
        app=QLabel(self.info['app'] or 'This window');app.setTextFormat(Qt.TextFormat.PlainText)
        app.setWordWrap(True);layout.addWidget(app)
        form_widget=QWidget();form=QFormLayout(form_widget);form.setSpacing(12);form.setContentsMargins(0,0,8,0)
        self.scope=QComboBox()
        if self.info['app']:self.scope.addItem('All windows of this app · remembered','app')
        self.scope.addItem('Only this window · until it closes','window')
        form.addRow('Apply to',self.scope)
        self.mode=QComboBox()
        for key,label in rules.MODES.items():self.mode.addItem(label,key)
        form.addRow('Show controls',self.mode)
        self.size=SliderControl(24,64);form.addRow('Button size',self.size)
        self.anchor=QComboBox()
        for key,label in rules.ANCHORS.items():self.anchor.addItem(label,key)
        form.addRow('Position',self.anchor)
        self.x=SliderControl(0,4000);self.y=SliderControl(0,4000)
        form.addRow('Horizontal inset',self.x);form.addRow('Vertical inset',self.y)
        self.proximity=SliderControl(12,400);form.addRow('Nearby distance',self.proximity)
        self.background=QComboBox()
        for key,label in rules.BACKGROUNDS.items():self.background.addItem(label,key)
        form.addRow('Button background',self.background)
        colors=QWidget();color_row=QHBoxLayout(colors);color_row.setContentsMargins(0,0,0,0)
        self.color_button=QPushButton();self.color_button.clicked.connect(self.choose_color)
        self.pick_button=QPushButton('Pick from screen…');self.pick_button.clicked.connect(self.pick_color)
        color_row.addWidget(self.color_button,1);color_row.addWidget(self.pick_button,1)
        form.addRow('Manual color',colors)
        background_hint=QLabel('Auto blends the solid background with the window underneath. '
                              'Manual covers it with your chosen color, including the gaps between buttons.')
        background_hint.setWordWrap(True);form.addRow(background_hint)
        form.addRow(DragSettings(self))
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(form_widget);scroll.setMinimumHeight(160);layout.addWidget(scroll,1)
        self.picker=DesktopPicker(self);self.picker.picked.connect(self.set_color);self.picker.finished.connect(self.picker_finished)
        self.live=QLabel();self.live.setWordWrap(True);self.live.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.live)
        hint=QLabel('All four buttons stay visible on the window while you edit. '
                    'Move the sliders to preview changes; Apply saves them. '
                    'Your chosen visibility takes effect when you close this editor.')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.reset=QPushButton('Reset this window to defaults');self.reset.clicked.connect(self.reset_window)
        self.reset.setToolTip('Preview the global window-control defaults for this window only. Apply to keep them.')
        layout.addWidget(self.reset)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        footer=QHBoxLayout();self.inherit=QPushButton('Use inherited settings');self.inherit.clicked.connect(self.use_inherited);footer.addWidget(self.inherit)
        self.reload=QPushButton('Reload');self.reload.clicked.connect(self.load);footer.addWidget(self.reload);footer.addStretch()
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Close)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setObjectName('primary')
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        self.buttons.rejected.connect(self.reject);footer.addWidget(self.buttons);layout.addLayout(footer)
        self.preview_process=QProcess(self)
        self.preview_process.finished.connect(self.preview_finished)
        self.preview_process.errorOccurred.connect(self.preview_failed)
        self.preview_timeout=QTimer(self);self.preview_timeout.setSingleShot(True);self.preview_timeout.setInterval(2000)
        self.preview_timeout.timeout.connect(self.preview_process.kill)
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.setInterval(20)
        self.preview_timer.timeout.connect(self.send_preview)
        self.heartbeat=QTimer(self);self.heartbeat.setInterval(900);self.heartbeat.timeout.connect(self.queue_preview)
        self.scope.currentIndexChanged.connect(self.scope_changed)
        for control in (self.mode,self.anchor,self.background):control.currentIndexChanged.connect(self.changed)
        for control in (self.size,self.x,self.y,self.proximity):control.valueChanged.connect(self.changed)
        self.load();self.heartbeat.start()

    def values(self):
        return dict(mode=self.mode.currentData(),size=self.size.value(),anchor=self.anchor.currentData(),
                    x=self.x.value(),y=self.y.value(),proximity=self.proximity.value(),
                    background=self.background.currentData(),background_color=self.background_color)

    def set_values(self,value):
        value=rules.validate(value)
        self.loading=True
        try:
            self.mode.setCurrentIndex(self.mode.findData(value['mode']));self.anchor.setCurrentIndex(self.anchor.findData(value['anchor']))
            for key in ('size','x','y','proximity'):getattr(self,key).setValue(value[key])
            self.background.setCurrentIndex(self.background.findData(value['background']))
            self.background_color=value['background_color'];self.update_color_controls()
        finally:self.loading=False
        self.proximity.setEnabled(value['mode']=='nearby');self.queue_preview()

    def changed(self,*_):
        if self.loading:return
        self.update_color_controls()
        self.remove_override=False;self.proximity.setEnabled(self.mode.currentData()=='nearby')
        self.status.setText('Previewing changes. Apply to save; Close discards unapplied changes.')
        self.queue_preview()

    def update_color_controls(self):
        manual=self.background.currentData()=='manual'
        self.color_button.setEnabled(manual and not self.picking);self.pick_button.setEnabled(manual and not self.picking)
        self.background.setEnabled(not self.picking)
        swatch=QPixmap(20,20);swatch.fill(QColor(self.background_color));self.color_button.setIcon(QIcon(swatch))
        self.color_button.setText(self.background_color.upper()+' · Choose…')

    def set_color(self,color):
        if not color.isValid():return
        self.background_color=color.name(QColor.NameFormat.HexRgb);self.changed()

    def choose_color(self):
        if self.color_dialog:
            self.color_dialog.raise_();self.color_dialog.activateWindow();return
        previous=self.background_color
        dialog=QColorDialog(QColor(previous),self);self.color_dialog=dialog
        dialog.setWindowTitle('Window controls background')
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
        dialog.currentColorChanged.connect(self.set_color)
        def finish(result):
            if result!=QDialog.DialogCode.Accepted:self.set_color(QColor(previous))
            self.color_dialog=None;dialog.deleteLater()
        dialog.finished.connect(finish);dialog.open()

    def pick_color(self):
        if self.picking:return
        self.picking=True;self.update_color_controls()
        self.status.setText('Click a color anywhere on the desktop. Escape cancels.')
        self.picker.start()

    def picker_finished(self,message):
        self.picking=False;self.update_color_controls()
        if not self.closing:self.status.setText(message)

    def scope_changed(self,*_):
        if self.loading or not self.valid:return
        self.remove_override=False
        scope=self.scope.currentData();key=self.info['app'] if scope=='app' else self.window_id
        self.inherit.setEnabled(key in self.documents[scope])
        self.status.setText('Apply will save for this app and replace this window’s override.' if scope=='app' and self.info['window_override'] else
                            'Apply will save for all windows of this app.' if scope=='app' else 'Apply will save for this window until it closes.')

    def load(self,*_):
        if self.picking:self.picker.cancel()
        self.valid=False;self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(False)
        self.inherit.setEnabled(False);self.reset.setEnabled(False)
        try:
            self.info=controller.window_info(self.window_id)
            self.settings,_=model.load();self.documents={};self.tokens={}
            for scope in ('app','window'):
                path,section=controller.rule_file(scope);data,self.tokens[scope]=rules.load(path,section)
                self.documents[scope]=data[section]
            width,height=self.info.get('size',[1000,700])
            self.x.setSliderMaximum(max(16,width-4*self.info['rule']['size']-24))
            self.y.setSliderMaximum(max(16,height-self.info['rule']['size']-8))
            self.valid=True;self.remove_override=False
            # Apply-to selects the destination, never the source. Always show
            # this window's effective settings, including its own override.
            self.set_values(self.info['rule']);self.scope_changed()
            self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(True);self.reset.setEnabled(True)
        except Exception as error:self.status.setText(str(error))

    def reset_window(self):
        if self.picking:self.picker.cancel()
        self.scope.setCurrentIndex(self.scope.findData('window'))
        self.remove_override=False;self.set_values(rules.effective(self.settings))
        self.status.setText('Default settings previewed for this window only. Apply to keep them.')

    def use_inherited(self):
        if self.picking:self.picker.cancel()
        scope=self.scope.currentData()
        inherited=self.documents['app'].get(self.info['app']) if scope=='window' else None
        self.set_values(rules.effective(self.settings,inherited));self.remove_override=True
        self.status.setText('Inherited settings previewed. Apply to remove this override.')

    def apply(self):
        try:
            scope=self.scope.currentData();value=None if self.remove_override else self.values()
            controller.save_rule(self.window_id,scope,value,self.tokens[scope],
                                 window_token=self.tokens['window'] if scope=='app' else None)
            self.load()
            self.status.setText('Applied. '+('Saved for this app and future logins.' if scope=='app' else 'This choice lasts until this window closes.'))
        except Exception as error:self.status.setText(str(error))

    def queue_preview(self):
        if self.closing or not self.valid:return
        self.preview_dirty=True;self.preview_timer.start()

    def send_preview(self):
        if self.closing or not self.valid or not self.isVisible():return
        if self.preview_process.state()!=QProcess.ProcessState.NotRunning:return
        self.preview_dirty=False
        payload=controller.preview_payload(self.window_id,self.preview_token,self.values())
        self.preview_process.start('hyprctl',['dispatch','xetalwindowclose:preview',payload]);self.preview_timeout.start()

    def preview_finished(self,code,*_):
        self.preview_timeout.stop()
        output=bytes(self.preview_process.readAllStandardOutput()).decode(errors='replace').strip()
        errors=bytes(self.preview_process.readAllStandardError()).decode(errors='replace').strip()
        if self.closing:return
        if code==0 and output=='ok':self.live.setText('● Live preview on your window')
        else:self.live.setText('Live preview unavailable: '+(errors or output or 'The compositor did not respond.')[-240:])
        if 'This window has closed' in output:
            self.valid=False;self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(False);self.reset.setEnabled(False);self.inherit.setEnabled(False)
        if self.preview_dirty:self.preview_timer.start(0)

    def preview_failed(self,*_):
        if not self.closing:self.live.setText('Live preview unavailable: '+self.preview_process.errorString())

    def end_preview(self):
        if self.closing:return
        self.closing=True;self.preview_timer.stop();self.heartbeat.stop();self.preview_timeout.stop()
        self.picker.cancel()
        if self.color_dialog:self.color_dialog.reject()
        if self.preview_process.state()!=QProcess.ProcessState.NotRunning:
            self.preview_process.kill();self.preview_process.waitForFinished(500)
        try:controller.end_preview(self.window_id,self.preview_token)
        except Exception:pass  # Native preview expires if the session/helper ends abruptly.

    def done(self,result):
        self.end_preview();super().done(result)


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
    timer=QTimer(app);timer.setInterval(1500);timer.timeout.connect(lambda:app.quit() if not (session/'.socket.sock').exists() else None);timer.start()
    app.aboutToQuit.connect(dialog.end_preview)
    dialog.show();return app.exec()


if __name__=='__main__':sys.exit(main())
