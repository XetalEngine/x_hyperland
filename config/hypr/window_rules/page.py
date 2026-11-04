"""Window Rules editor shared by global controls and the window gear dialog."""
import copy
import json
import uuid
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget,
    QScrollArea, QLabel, QLineEdit, QComboBox, QSpinBox, QCheckBox, QPushButton, QListWidget,
    QListWidgetItem, QDialogButtonBox, QGroupBox, QMessageBox)
from . import model, controller
from effects.window_close import rules as buttons, controller as controls


def combo(choices, value):
    widget = QComboBox()
    for key, caption in choices: widget.addItem(caption, key)
    widget.setCurrentIndex(max(0, widget.findData(value)))
    return widget


def spin(value, low, high, suffix='', automatic=None):
    widget = QSpinBox(); widget.setRange(low, high); widget.setValue(value); widget.setSuffix(suffix)
    if automatic: widget.setSpecialValueText(automatic)
    return widget


class Editor(QDialog):
    def __init__(self, entry, parent=None):
        super().__init__(parent); self.entry = copy.deepcopy(entry)
        self.setWindowTitle('Edit window rule'); self.resize(700, 790)
        outer = QVBoxLayout(self); form = QFormLayout(); outer.addLayout(form)
        self.name = QLineEdit(entry['name']); form.addRow('Rule name', self.name)
        self.app = QLineEdit(entry['app']); form.addRow('Application ID', self.app)
        self.title = QLineEdit(entry['title']); form.addRow('Initial window title', self.title)
        hint = QLabel('Matches are case sensitive. Use * for any text or ? for one character. Leave title blank for every window.'); hint.setWordWrap(True); form.addRow(hint)
        pick = QPushButton('Choose an open application…'); pick.clicked.connect(self.pick); form.addRow(pick)
        tabs = QTabWidget(); outer.addWidget(tabs, 1)
        container = QWidget(); behavior = QFormLayout(container)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(container); tabs.addTab(scroll, 'Behavior')
        self.fields = {}
        for key, caption, choices in [
            ('layout', 'Window mode', [('inherit','Inherit'),('tile','Tiled'),('floating','Floating')]),
            ('position', 'Position', [('inherit','Remember / automatic'),('center','Centered'),('custom','Custom · relative to monitor')]),
            ('fullscreen', 'Initial state', [('inherit','Inherit'),('normal','Normal'),('maximized','Maximized'),('fullscreen','Fullscreen')]),
            ('pin', 'Visible on every workspace', [('inherit','Inherit'),('on','On · floating windows'),('off','Off')]),
            ('focus', 'Take focus when opened', [('inherit','Inherit'),('on','On'),('off','Off')])]:
            widget = combo(choices, entry[key]); self.fields[key] = widget; behavior.addRow(caption, widget)
        for key, caption, low, high, suffix, automatic in [
            ('workspace','Workspace',0,100,'','Current workspace'), ('width','Width',0,32768,' px','Automatic'),
            ('height','Height',0,32768,' px','Automatic'), ('x','Horizontal position',-32768,32768,' px',None),
            ('y','Vertical position',-32768,32768,' px',None), ('opacity','Opacity',-1,100,' %','Inherit'),
            ('rounding','Corner radius',-1,100,' px','Inherit'), ('border','Border width',-1,20,' px','Inherit')]:
            widget=spin(entry[key],low,high,suffix,automatic); self.fields[key]=widget; behavior.addRow(caption,widget)
        self.monitor=QLineEdit(entry['monitor']); self.monitor.setPlaceholderText('Automatic · or an output such as DP-1'); behavior.addRow('Monitor',self.monitor)
        hint=QLabel('Size and position apply to floating windows. Workspace force tile / force floating overrides the window mode.');hint.setWordWrap(True);behavior.addRow(hint)
        box=QWidget(); layout=QVBoxLayout(box); tabs.addTab(box,'Control buttons')
        self.custom=QGroupBox('Override this application’s button settings');self.custom.setCheckable(True);self.custom.setChecked(entry['controls'] is not None);layout.addWidget(self.custom)
        fields=QFormLayout(self.custom); self.controls={}; value=entry['controls'] or buttons.DEFAULTS
        for key, caption, choices in [('mode','Show controls',buttons.MODES),('anchor','Position',buttons.ANCHORS),('background','Background',buttons.BACKGROUNDS)]:
            widget=combo(choices.items(),value[key]); self.controls[key]=widget; fields.addRow(caption,widget)
        for key,caption,lo,hi in [('size','Button size',10,64),('x','Horizontal inset',0,4000),('y','Vertical inset',0,4000),('proximity','Nearby distance',12,400)]:
            widget=spin(value[key],lo,hi,' px');self.controls[key]=widget;fields.addRow(caption,widget)
        self.color=QLineEdit(value['background_color']);fields.addRow('Manual color · #RRGGBB',self.color)
        hint=QLabel('Workspace Force modifier buttons On / Off takes priority. An explicit setting for one live window takes priority over this rule.');hint.setWordWrap(True);layout.addWidget(hint);layout.addStretch()
        self.status=QLabel(); self.status.setWordWrap(True);outer.addWidget(self.status)
        actions=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(self.save);actions.rejected.connect(self.reject);outer.addWidget(actions)

    def pick(self):
        try: clients=json.loads(controls.hypr('-j','clients'))
        except Exception as error: self.status.setText(str(error)); return
        dialog=QDialog(self);dialog.setWindowTitle('Choose an application');layout=QVBoxLayout(dialog);listing=QListWidget();layout.addWidget(listing)
        for app in sorted({c.get('initialClass') or c.get('class') for c in clients if c.get('initialClass') or c.get('class')}): listing.addItem(app)
        listing.itemDoubleClicked.connect(lambda _:dialog.accept())
        actions=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(actions)
        actions.accepted.connect(dialog.accept);actions.rejected.connect(dialog.reject)
        if dialog.exec() and listing.currentItem():
            app=listing.currentItem().text();self.app.setText(app)
            if self.name.text()=='New rule':self.name.setText(app)
            existing=buttons.load()[0]['apps'].get(app)
            if existing and self.entry['controls'] is None:
                self.custom.setChecked(True)
                for key,widget in self.controls.items():
                    if isinstance(widget,QComboBox):widget.setCurrentIndex(widget.findData(existing[key]))
                    else:widget.setValue(existing[key])
                self.color.setText(existing['background_color'])

    def save(self):
        value=dict(self.entry,name=self.name.text().strip(),app=self.app.text().strip(),title=self.title.text(),monitor=self.monitor.text().strip())
        for key,widget in self.fields.items(): value[key]=widget.currentData() if isinstance(widget,QComboBox) else widget.value()
        value['controls']=None
        if self.custom.isChecked():
            value['controls']={key:widget.currentData() if isinstance(widget,QComboBox) else widget.value() for key,widget in self.controls.items()}
            value['controls']['background_color']=self.color.text()
        try:self.entry=model.validate({'version':1,'rules':[value]})['rules'][0]
        except ValueError as error:self.status.setText(str(error));return
        self.accept()


class Save(QThread):
    completed=pyqtSignal(object,str)
    def __init__(self,document,token,parent):super().__init__(parent);self.document=document;self.token=token
    def run(self):
        try:self.completed.emit(controller.save(self.document,self.token),'')
        except Exception as error:self.completed.emit(None,str(error))


class RulesPage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.worker=None;self.loading=False
        outer=QVBoxLayout(self)
        hint=QLabel('Set app-specific behavior and controls. Later matching rules win. Workspace force modes take priority. Behavior changes apply when windows next open; button changes apply immediately.');hint.setWordWrap(True);outer.addWidget(hint)
        self.search=QLineEdit();self.search.setPlaceholderText('Find a rule or application…');self.search.textChanged.connect(self.filter);outer.addWidget(self.search)
        self.list=QListWidget();self.list.itemChanged.connect(self.changed);self.list.itemDoubleClicked.connect(lambda _:self.edit());outer.addWidget(self.list,1)
        row=QHBoxLayout();outer.addLayout(row)
        for caption,fn in [('Add…',self.add),('Edit…',self.edit),('Duplicate',self.duplicate),('Remove',self.remove),('Move up',lambda:self.move(-1)),('Move down',lambda:self.move(1))]:
            b=QPushButton(caption);b.clicked.connect(fn);row.addWidget(b)
        self.status=QLabel();self.status.setWordWrap(True);outer.addWidget(self.status)
        row=QHBoxLayout();outer.addLayout(row)
        reload=QPushButton('Reload');reload.clicked.connect(self.reload_requested);row.addWidget(reload);row.addStretch()
        self.apply=QPushButton('Apply window rules');self.apply.setObjectName('primary');self.apply.clicked.connect(self.save);row.addWidget(self.apply)
        close=QPushButton('Close');close.clicked.connect(lambda:self.window().close());row.addWidget(close)
        self.reload()

    def reload(self):
        try:self.document,self.token=model.load();self.baseline=copy.deepcopy(self.document);self.populate();self.status.clear()
        except (OSError,ValueError) as error:self.document=self.baseline={'version':1,'rules':[]};self.token='';self.status.setText(str(error))

    def populate(self,index=0):
        self.loading=True;self.list.clear()
        for rule in self.document['rules']:
            item=QListWidgetItem(rule['name']+'  ·  '+rule['app']+('  ·  '+rule['title'] if rule['title'] else ''))
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if rule['enabled'] else Qt.CheckState.Unchecked);self.list.addItem(item)
        self.list.setCurrentRow(index);self.loading=False;self.filter();self.changed()

    @property
    def dirty(self):return self.document!=self.baseline
    def changed(self,*_):
        if self.loading:return
        for i,rule in enumerate(self.document['rules']):rule['enabled']=self.list.item(i).checkState()==Qt.CheckState.Checked
        self.apply.setEnabled(self.dirty)
    def filter(self,*_):
        for i in range(self.list.count()):self.list.item(i).setHidden(self.search.text().casefold() not in self.list.item(i).text().casefold())
    def add(self):
        editor=Editor(dict(model.DEFAULT,id=uuid.uuid4().hex),self)
        if editor.exec():self.document['rules'].append(editor.entry);self.populate(len(self.document['rules'])-1)
    def edit(self):
        index=self.list.currentRow()
        if index<0:return
        editor=Editor(self.document['rules'][index],self)
        if editor.exec():self.document['rules'][index]=editor.entry;self.populate(index)
    def duplicate(self):
        index=self.list.currentRow()
        if index<0:return
        rule=copy.deepcopy(self.document['rules'][index]);rule.update(id=uuid.uuid4().hex,name=rule['name']+' copy');self.document['rules'].insert(index+1,rule);self.populate(index+1)
    def remove(self):
        index=self.list.currentRow()
        if index>=0:self.document['rules'].pop(index);self.populate(min(index,self.list.count()-2))
    def move(self,delta):
        index=self.list.currentRow();target=index+delta
        if index>=0 and 0<=target<len(self.document['rules']):self.document['rules'].insert(target,self.document['rules'].pop(index));self.populate(target)
    def can_close(self):
        if self.worker and self.worker.isRunning():return False
        return not self.dirty or QMessageBox.question(self,'Unsaved window rules','Discard your unapplied window rules?',QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Discard
    def reload_requested(self):
        if self.can_close():self.reload()
    def save(self):
        self.setEnabled(False);self.status.setText('Validating and applying…');self.worker=Save(copy.deepcopy(self.document),self.token,self);self.worker.completed.connect(self.saved);self.worker.start()
    def saved(self,result,error):
        self.setEnabled(True)
        if error:self.status.setText(error)
        else:self.document,self.token=result;self.baseline=copy.deepcopy(self.document);self.populate();self.status.setText('Saved. Workspace overrides remain in effect.')
