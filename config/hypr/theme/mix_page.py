"""One quick editor for the same settings exposed by the detailed theme tabs."""
from PyQt6.QtCore import QTimer,QFileSystemWatcher
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,
    QGroupBox,QComboBox,QCheckBox,QPushButton,QLabel,QScrollArea,QMessageBox)
import quick_mix
import selection_marker
import runtime
import bar_styles
from effects.minimize.gallery import DesignButton


def note(text):
    widget=QLabel(text);widget.setWordWrap(True);widget.setObjectName('muted');return widget


class MixMatchPage(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.busy=self.dirty=self.loading=False
        self.baseline={};self.draft={};self.token=None;self.conflicts=[];self.fields={};self.last_trail='follow'
        root=QVBoxLayout(self);root.setContentsMargins(12,12,12,12)
        title=QLabel('Mix & match');title.setObjectName('brand');root.addWidget(title)
        root.addWidget(note('Your current settings, together. Apply a theme first, then combine its parts here. Changes also appear in their original tabs and stay active until you change them.'))
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.body=QWidget();grid=QGridLayout(self.body);grid.setSpacing(16)
        groups=[('Desktop & navigation',('waybar','dock','launcher','layout','marker'),owner.start_menu_page),
                ('Pointer & mouse effects',('cursor','trail','ripple'),owner.appearance),
                ('File transfers',('transfer','transfer_animation'),owner.file_transfer),
                ('Switching windows',('switcher',),owner.task_switcher)]
        for i,(title,keys,page) in enumerate(groups):
            box=QGroupBox(title.replace('&','&&'));column=QVBoxLayout(box);form=QFormLayout();form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            if i==1:
                self.trail_enabled=QCheckBox('Enable mouse trail');self.trail_enabled.setAccessibleName('Mix & match · Enable mouse trail')
                self.trail_enabled.toggled.connect(self.toggle_trail);column.addWidget(self.trail_enabled)
            for key in keys:
                caption,_,_,choices=quick_mix.FIELDS[key]
                if key=='dock':
                    field=DesignButton();field.valueChanged.connect(lambda value:self.edit('dock',value));form.addRow(caption,field)
                elif choices is None:
                    field=QCheckBox(caption);field.toggled.connect(lambda value,k=key:self.edit(k,value));form.addRow(field)
                else:
                    field=QComboBox();field.setMinimumContentsLength(15);field.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                    for value,text in choices.items():field.addItem(text,value)
                    field.currentIndexChanged.connect(lambda _,k=key:self.edit(k,self.fields[k].currentData()));form.addRow(caption.replace('&','&&'),field)
                field.setAccessibleName('Mix & match · '+caption);self.fields[key]=field
            column.addLayout(form)
            if i==0:
                self.bar_description=note('');column.addWidget(self.bar_description)
                self.marker_preview=selection_marker.preview();column.addWidget(self.marker_preview)
                column.addWidget(note('Mix any Waybar and dock design with your desktop theme. Dock timing, position and size stay as you set them.'))
                dock_link=QPushButton('Open dock settings');dock_link.clicked.connect(self.open_dock);column.addWidget(dock_link)
                column.addWidget(note('Selection marker adds an optional edge in Fusion Files. Off keeps the usual selection highlight.'))
            elif i==1:
                self.active_trail=note('');column.addWidget(self.active_trail)
                column.addWidget(note('Choose any themed trail, a general effect, or Off. Cursor artwork is independent.'))
            elif i==2:column.addWidget(note('The transfer style includes its animation design. Detailed timing, size and information choices are kept.'))
            else:column.addWidget(note('Change how your windows are arranged in the switcher. Its other options stay as you set them.'))
            column.addStretch();link=QPushButton('Open detailed settings');link.clicked.connect(lambda _,p=page:self.open_details(p));column.addWidget(link)
            grid.addWidget(box,i//2,i%2)
        grid.setColumnStretch(0,1);grid.setColumnStretch(1,1);grid.setRowStretch(2,1)
        scroll.setWidget(self.body);root.addWidget(scroll,1)
        self.status=note('This is a quick editor, not a separate preset.');root.addWidget(self.status)
        row=QHBoxLayout();self.keep=QPushButton('Keep my choices');self.keep.clicked.connect(self.keep_choices);row.addWidget(self.keep)
        row.addStretch();self.reload=QPushButton('Reload');self.reload.clicked.connect(lambda:self.refresh(True));row.addWidget(self.reload)
        self.discard=QPushButton('Discard');self.discard.clicked.connect(lambda:self.fill(self.baseline));row.addWidget(self.discard)
        self.apply=QPushButton('Apply adjustments');self.apply.setObjectName('primary');self.apply.clicked.connect(self.save);row.addWidget(self.apply);root.addLayout(row)
        self.refresh_timer=QTimer(self);self.refresh_timer.setSingleShot(True);self.refresh_timer.setInterval(100);self.refresh_timer.timeout.connect(self.refresh)
        paths=[runtime.ROOT,*(runtime.ROOT.parent/name for name in ('cursors','file_jobs','switcher','effects/minimize'))]
        self.watcher=QFileSystemWatcher([str(p) for p in paths if p.is_dir()],self)
        self.watcher.directoryChanged.connect(lambda _:self.refresh_timer.start() if self.isVisible() else None)
        self.refresh()
    def showEvent(self,event):self.refresh();super().showEvent(event)
    def hideEvent(self,event):self.refresh_timer.stop();super().hideEvent(event)
    def open_details(self,page):
        if page is self.owner.appearance:page.tabs.setCurrentWidget(page.mouse)
        self.owner.tabs.setCurrentWidget(page)
    def open_dock(self):
        page=self.owner.appearance;page.tabs.setCurrentWidget(page.minimize)
        self.owner.tabs.setCurrentWidget(page)
    def fill(self,values):
        self.loading=True;self.draft=dict(values)
        for key,field in self.fields.items():
            if isinstance(field,QCheckBox):field.setChecked(values[key])
            elif isinstance(field,DesignButton):field.setValue(values[key])
            else:field.setCurrentIndex(field.findData(values[key]))
        self.loading=False;self.changed()
    def edit(self,key,value):
        if self.loading:return
        self.draft[key]=value;self.conflicts=[k for k in self.conflicts if k!=key];self.changed()
    def toggle_trail(self,enabled):
        if not self.loading:self.fill(dict(self.draft,trail=self.last_trail if enabled else 'none'))
    def changed(self):
        self.dirty=self.draft!=self.baseline
        self.conflicts=[key for key in self.conflicts if self.draft.get(key)!=self.baseline.get(key)]
        if self.draft:
            if self.draft['trail']!='none':self.last_trail=self.draft['trail']
            self.trail_enabled.blockSignals(True);self.trail_enabled.setChecked(self.draft['trail']!='none');self.trail_enabled.blockSignals(False)
        if self.draft:self.bar_description.setText(bar_styles.DESCRIPTIONS[bar_styles.resolve(self.draft['waybar'],runtime.design())])
        if self.draft:selection_marker.style_preview(self.marker_preview,self.draft['marker'])
        self.body.setEnabled(not self.busy and bool(self.baseline))
        self.apply.setEnabled(self.dirty and not self.busy and not self.conflicts)
        self.discard.setEnabled(self.dirty and not self.busy);self.reload.setEnabled(not self.busy)
        self.keep.setVisible(bool(self.conflicts));self.keep.setEnabled(not self.busy)
    def refresh(self,force=False):
        if self.busy or (hasattr(self.owner,'mix_page') and self.owner.busy):
            # Preset application refreshes other pages asynchronously. A file
            # notification or tab change during that work must be retried.
            if self.isVisible():self.refresh_timer.start()
            return
        if force and self.dirty and QMessageBox.question(self,'Reload quick settings?','Discard these unapplied adjustments and reload the current settings?',QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Discard:return
        try:
            saved,token,_=quick_mix.read()
            if token==self.token and not force:return
            edited,conflicts=quick_mix.merge(self.baseline,self.draft,saved) if self.baseline and not force else (saved,[])
            if not force:conflicts=list(dict.fromkeys([*conflicts,*(k for k in self.conflicts if edited[k]!=saved[k])]))
            self.baseline,self.token=saved,token;self.conflicts=conflicts;self.fill(edited)
            self.show_active_trail()
            self.status.setText('Also changed elsewhere: '+', '.join(quick_mix.FIELDS[k][0] for k in conflicts)+'. Reload or keep your choices.' if conflicts else 'Showing the current settings. Apply adjustments updates the same settings used by the detailed tabs.')
        except (ValueError,OSError) as exc:self.failed(str(exc))
    def show_active_trail(self):
        from cursors import effects,model
        trail=self.baseline['trail'];design=runtime.design()
        self.active_trail.setText('Active trail: '+model.TRAILS[effects.resolve(trail,design)]+(' · follows '+runtime.DESIGNS[design] if trail=='follow' else ''))
    def keep_choices(self):self.conflicts=[];self.changed();self.status.setText('Your choices are ready to apply.')
    def save(self):
        if self.owner.busy:return
        if self.owner.other_pending_mix_edits():
            self.status.setText('Apply or discard pending edits in the other Theme tabs first. Your quick adjustments are kept.');return
        self.refresh()
        if not self.dirty or self.conflicts:return
        values,baseline,token=dict(self.draft),dict(self.baseline),self.token
        self.busy=True;self.changed();self.owner.changed();self.status.setText('Applying adjustments…')
        self.owner.async_run(lambda:quick_mix.apply(values,baseline,token),self.saved,self.failed)
    def saved(self,result):
        self.baseline,self.token,selected=result;self.busy=False;self.conflicts=[];self.fill(self.baseline)
        self.show_active_trail()
        self.owner.components_saved('Mix & match',selected,self.token)
        self.status.setText('Applied. These choices are shared with the detailed tabs; no separate preset was created.')
    def failed(self,error):
        self.busy=False;self.changed();self.status.setText(str(error))
        if hasattr(self.owner,'mix_page'):self.owner.changed()
