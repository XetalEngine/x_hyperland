"""Shared title-grip controls in the global and per-app window editors."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGroupBox,QVBoxLayout,QFormLayout,QHBoxLayout,QWidget,QLabel,QSlider,QSpinBox,QPushButton
from . import drag_settings


class DragSettings(QGroupBox):
    def __init__(self,parent=None):
        super().__init__('Floating title drag · all windows',parent)
        layout=QVBoxLayout(self)
        hint=QLabel('A click goes straight to the app. To move a floating window without Super, '
                    'hold near its top and move beyond this distance. The short hold protects tab buttons from accidental drags.')
        hint.setWordWrap(True);layout.addWidget(hint)
        form=QFormLayout();layout.addLayout(form);self.controls={}
        for key,title,low,high,suffix in (('distance','Movement before dragging',1,24,' px'),('hold_ms','Hold before dragging',0,500,' ms')):
            row=QWidget();line=QHBoxLayout(row);line.setContentsMargins(0,0,0,0)
            slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(low,high)
            spin=QSpinBox();spin.setRange(low,high);spin.setSuffix(suffix);spin.setKeyboardTracking(False)
            slider.valueChanged.connect(spin.setValue);spin.valueChanged.connect(slider.setValue)
            line.addWidget(slider,1);line.addWidget(spin);form.addRow(title,row);self.controls[key]=spin
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();layout.addLayout(row)
        for text,callback in (('System defaults',self.defaults),('Reload',self.load),('Apply drag settings',self.apply)):
            button=QPushButton(text);button.clicked.connect(callback);row.addWidget(button)
        self.load()

    def set_values(self,values):
        for key,value in values.items():self.controls[key].setValue(value)

    def load(self):
        try:
            values,self.token=drag_settings.load();self.set_values(values);self.status.clear()
        except (OSError,ValueError) as error:self.token=None;self.status.setText(str(error))

    def defaults(self):
        self.set_values(drag_settings.DEFAULTS);self.status.setText('Defaults selected. Apply drag settings to save them.')

    def apply(self):
        try:
            _,self.token=drag_settings.save({key:control.value() for key,control in self.controls.items()},self.token)
            self.status.setText('Applied to all floating title grips. Super-drag is unchanged.')
        except (OSError,ValueError) as error:self.status.setText(str(error))
