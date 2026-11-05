"""Visual icon libraries and individual replacements. Previews never apply drafts."""
from copy import deepcopy
from pathlib import Path
from PyQt6.QtCore import Qt, QSize, QRectF
from PyQt6.QtGui import QIcon, QPainter, QColor, QPen, QFont
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTabWidget,
    QListWidget,QListWidgetItem,QStyledItemDelegate,QStyle,QLineEdit,QComboBox,QFileDialog,
    QGridLayout,QFrame,QScrollArea,QInputDialog,QMessageBox,QSizePolicy)
from . import art,model
import runtime


def button(text,callback):
    result=QPushButton(text);result.clicked.connect(callback);return result


class SetDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected=bool(option.state&QStyle.StateFlag.State_Selected);hover=bool(option.state&QStyle.StateFlag.State_MouseOver)
        p=runtime.colors();rect=QRectF(option.rect).adjusted(3,3,-3,-3)
        painter.setPen(QPen(QColor(p['Accent'] if selected else p['Midlight']),1.5 if selected else 1))
        painter.setBrush(QColor(p['Highlight'] if selected else p['AlternateBase'] if hover else p['Base']));painter.drawRoundedRect(rect,13,13)
        painter.setPen(QColor(p['Text']));font=QFont(runtime.ui_font(),10);font.setBold(selected);painter.setFont(font)
        painter.drawText(rect.adjusted(12,8,-12,-60),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,index.data())
        for i,path in enumerate(index.data(Qt.ItemDataRole.UserRole+1) or []):
            QIcon(path).paint(painter,int(rect.left()+12+i*44),int(rect.top()+35),38,38)
        painter.restore()
    def sizeHint(self,option,index):return QSize(246,88)


class IconPreview(QFrame):
    def __init__(self):
        super().__init__();self.setObjectName('iconLibraryPreview')
        root=QVBoxLayout(self);root.setContentsMargins(20,16,20,16)
        self.heading=QLabel();self.heading.setObjectName('section');root.addWidget(self.heading)
        self.description=QLabel();self.description.setWordWrap(True);self.description.setObjectName('muted');root.addWidget(self.description)
        scroll=QScrollArea();scroll.setFrameShape(QFrame.Shape.NoFrame);scroll.setWidgetResizable(True)
        body=QWidget();self.grid=QGridLayout(body);self.grid.setSpacing(12);self.labels={}
        names=['system-file-manager','computer','utilities-terminal','web-browser','accessories-text-editor','preferences-system',
            'user-home','user-desktop','folder-documents','folder-download','folder-pictures','folder-music',
            'folder-videos','user-trash-full','drive-harddisk','drive-removable-media-usb','network-workgroup','xetal-kvm-settings',
            'text-x-generic','image-x-generic','audio-x-generic','video-x-generic','application-pdf','package-x-generic']
        for i,name in enumerate(names):
            tile=QWidget();box=QVBoxLayout(tile);box.setContentsMargins(1,2,1,4);box.setSpacing(3)
            picture=QLabel();picture.setAlignment(Qt.AlignmentFlag.AlignCenter);picture.setMinimumHeight(62)
            title=QLabel(art.CATALOG[name][0]);title.setWordWrap(True);title.setAlignment(Qt.AlignmentFlag.AlignHCenter);title.setObjectName('muted')
            box.addWidget(picture);box.addWidget(title);self.grid.addWidget(tile,i//6,i%6);self.labels[name]=picture
        for c in range(6):self.grid.setColumnStretch(c,1)
        self.grid.setRowStretch(4,1);scroll.setWidget(body);root.addWidget(scroll,1)
        hint=QLabel('Launcher · Desktop icons · Fusion Files · File choosers');hint.setObjectName('muted');hint.setWordWrap(True);root.addWidget(hint)
    def show_choice(self,value):
        design=runtime.design();key=value['system'];other=model.resolve_other(value['other'],runtime.mode())
        actual=design if key=='follow' else key[8:] if key.startswith('builtin:') else ''
        self.heading.setText(('Following '+art.STYLES[actual][0]) if key=='follow' else art.STYLES[actual][0] if actual else other if key=='other' else key[6:])
        self.description.setText(art.DESCRIPTIONS[actual] if actual else 'A complete icon set for your system and applications. Individual choices stay on top.')
        for name,picture in self.labels.items():
            path=model.preview_path(value,name,design,runtime.mode());picture.setPixmap(QIcon(path).pixmap(60,60));picture.setToolTip(art.CATALOG[name][0])


class IconsPage(QWidget):
    def __init__(self,async_run):
        super().__init__();self.async_run=async_run;self.busy=self.dirty=self.loading=False
        self.load_error=''
        try:model.ensure();self.baseline,self.token=model.load()
        except (OSError,ValueError) as error:
            self.baseline=deepcopy(model.DEFAULTS);self.token=model.token(model.ROOT/'theme/icons.json');self.load_error=str(error)
        self.draft=deepcopy(self.baseline)
        root=QVBoxLayout(self);root.setContentsMargins(12,10,12,10)
        heading=QLabel('Icons');heading.setObjectName('brand');root.addWidget(heading)
        description=QLabel('Give your folders and Fusion tools their own character. Mix any icon design with any desktop theme.');description.setWordWrap(True);root.addWidget(description)
        self.tabs=QTabWidget();root.addWidget(self.tabs,1)
        self.make_system();self.make_other();self.make_individual()
        self.status=QLabel('Choose a set to preview it, then Apply icons.');self.status.setWordWrap(True);self.status.setObjectName('muted');root.addWidget(self.status)
        actions=QHBoxLayout();actions.addWidget(button('Defaults',lambda:self.fill(model.DEFAULTS)));actions.addStretch()
        self.reload_button=button('Reload',lambda:self.refresh(True));actions.addWidget(self.reload_button)
        self.discard_button=button('Discard',lambda:self.fill(self.baseline));actions.addWidget(self.discard_button)
        self.apply_button=button('Apply icons',self.save);self.apply_button.setObjectName('primary');actions.addWidget(self.apply_button);root.addLayout(actions)
        self.fill(self.baseline)
        if self.load_error:self.status.setText(self.load_error+' Choose icons and apply to replace the saved choices.')

    def make_system(self):
        page=QWidget();box=QVBoxLayout(page);row=QHBoxLayout();box.addLayout(row,1)
        self.system_list=QListWidget();self.system_list.setMinimumWidth(240);self.system_list.setMaximumWidth(290);self.system_list.setItemDelegate(SetDelegate(self.system_list));self.system_list.setSpacing(3)
        row.addWidget(self.system_list);self.preview=IconPreview();row.addWidget(self.preview,1)
        self.aftermarket=QComboBox();self.aftermarket.setAccessibleName('Installed system icon set')
        bottom=QHBoxLayout();bottom.addWidget(QLabel('Aftermarket set'));bottom.addWidget(self.aftermarket,1);bottom.addWidget(button('Import icon set…',self.import_pack));box.addLayout(bottom)
        self.system_list.currentItemChanged.connect(self.system_selected);self.aftermarket.currentIndexChanged.connect(self.aftermarket_selected)
        self.tabs.addTab(page,'System Icons')

    def make_other(self):
        page=QWidget();box=QVBoxLayout(page)
        text=QLabel('Icons for other applications and any symbols your system set does not include. Choose an installed set or import an extracted icon-set folder.');text.setWordWrap(True);box.addWidget(text)
        row=QHBoxLayout();self.other_list=QListWidget();self.other_list.setMinimumWidth(250);self.other_list.setMaximumWidth(310);self.other_list.setItemDelegate(SetDelegate(self.other_list));row.addWidget(self.other_list)
        panel=QWidget();right=QVBoxLayout(panel);self.other_title=QLabel();self.other_title.setObjectName('section');right.addWidget(self.other_title)
        self.other_details=QLabel();self.other_details.setWordWrap(True);self.other_details.setObjectName('muted');right.addWidget(self.other_details)
        self.other_grid=QGridLayout();right.addLayout(self.other_grid);self.other_images={}
        for i,(name,label) in enumerate([('firefox','Browser'),('org.kde.kate','Editor'),('vlc','Media'),('discord','Chat'),('steam','Games'),('org.gnome.Calculator','Calculator'),('folder','Folders'),('user-trash','Trash'),('utilities-terminal','Terminal'),('preferences-system','Settings'),('application-pdf','Documents'),('image-x-generic','Pictures')]):
            widget=QLabel();widget.setAlignment(Qt.AlignmentFlag.AlignCenter);widget.setMinimumSize(68,68)
            title=QLabel(label);title.setAlignment(Qt.AlignmentFlag.AlignCenter);self.other_grid.addWidget(widget,(i//4)*2,i%4);self.other_grid.addWidget(title,(i//4)*2+1,i%4);self.other_images[name]=widget
        right.addStretch();right.addWidget(button('Use this set for System Icons too',self.use_other_system));row.addWidget(panel,1);box.addLayout(row,1)
        bottom=QHBoxLayout();bottom.addWidget(button('Import icon set…',self.import_pack));bottom.addWidget(button('Refresh installed sets',self.reload_sets));bottom.addStretch();box.addLayout(bottom)
        self.other_list.currentItemChanged.connect(self.other_selected);self.tabs.addTab(page,'Other Icons')

    def make_individual(self):
        page=QWidget();root=QVBoxLayout(page);searchrow=QHBoxLayout()
        self.filter=QLineEdit();self.filter.setPlaceholderText('Find an icon, folder or file type…');searchrow.addWidget(self.filter,1)
        self.category=QComboBox();self.category.addItems(['All icons','Places','Devices','Apps','Files','Customized']);searchrow.addWidget(self.category)
        searchrow.addWidget(button('Add icon name…',self.add_name));root.addLayout(searchrow)
        row=QHBoxLayout();self.individual=QListWidget();self.individual.setIconSize(QSize(36,36));self.individual.setSpacing(2);row.addWidget(self.individual,1)
        editor=QWidget();editor.setMinimumWidth(250);editor.setMaximumWidth(370);form=QVBoxLayout(editor)
        self.single_image=QLabel();self.single_image.setMinimumHeight(156);self.single_image.setAlignment(Qt.AlignmentFlag.AlignCenter);form.addWidget(self.single_image)
        self.single_name=QLabel();self.single_name.setAlignment(Qt.AlignmentFlag.AlignCenter);self.single_name.setWordWrap(True);self.single_name.setObjectName('section');form.addWidget(self.single_name)
        self.single_detail=QLabel();self.single_detail.setWordWrap(True);self.single_detail.setObjectName('muted');form.addWidget(self.single_detail)
        self.choose_button=button('Choose image…',self.choose_image);form.addWidget(self.choose_button)
        self.single_set=QComboBox();self.single_set.setAccessibleName('Design for this icon')
        for key,(name,*_) in art.STYLES.items():self.single_set.addItem(name,key)
        form.addWidget(QLabel('Or borrow from a Fusion design'));form.addWidget(self.single_set)
        self.borrow_button=button('Use this design for this icon',self.borrow);form.addWidget(self.borrow_button)
        self.reset_button=button('Reset this icon',self.reset_icon);form.addWidget(self.reset_button);form.addStretch()
        form.addWidget(button('Reset all individual icons',self.reset_individual));row.addWidget(editor);root.addLayout(row,1)
        hint=QLabel('Individual choices override both sets. Existing shortcut-specific icons and file thumbnails are kept.');hint.setObjectName('muted');hint.setWordWrap(True);root.addWidget(hint)
        self.individual.currentItemChanged.connect(self.single_selected);self.filter.textChanged.connect(self.filter_icons);self.category.currentTextChanged.connect(self.filter_icons)
        self.tabs.addTab(page,'Individual Icons');self.extra_names=set()

    def set_card(self,widget,title,key,paths):
        item=QListWidgetItem(title);item.setData(Qt.ItemDataRole.UserRole,key);item.setData(Qt.ItemDataRole.UserRole+1,paths);widget.addItem(item)

    def reload_sets(self):
        self.available=model.installed();model.lookup.cache_clear();self.rebuild_sets();self.changed()

    def rebuild_sets(self):
        self.loading=True;self.available=model.installed();self.system_list.clear();self.other_list.clear();self.aftermarket.clear();paths=tuple(model.search_paths())
        sample=['folder','utilities-terminal','web-browser','accessories-text-editor','preferences-system']
        for key,title in [('follow','Follow desktop theme'),*[('builtin:'+key,name) for key,(name,*_) in art.STYLES.items()],('other','Use Other Icons')]:
            value={**self.draft,'system':key,'overrides':{}}
            self.set_card(self.system_list,title,key,[model.preview_path(value,n,runtime.design(),runtime.mode()) for n in sample])
        self.aftermarket.addItem('Choose an installed set…','')
        for key,entry in self.available.items():self.aftermarket.addItem(entry['name'],key)
        for key,title in [('auto','Current classics · Papirus'),*[('theme:'+key,item['name']) for key,item in self.available.items()]]:
            theme=model.resolve_other(key,runtime.mode());self.set_card(self.other_list,title,key,[model.lookup(theme,n,paths) for n in ['folder','firefox','vlc','utilities-terminal','preferences-system']])
        self.loading=False;self.select_sets()

    def select_sets(self):
        self.loading=True
        for widget,key in [(self.system_list,self.draft['system']),(self.other_list,self.draft['other'])]:
            widget.setCurrentRow(next((i for i in range(widget.count()) if widget.item(i).data(Qt.ItemDataRole.UserRole)==key),-1))
        self.aftermarket.setCurrentIndex(max(0,self.aftermarket.findData(self.draft['system'][6:] if self.draft['system'].startswith('theme:') else '')))
        self.loading=False

    def fill(self,value):
        self.draft=deepcopy(value);self.rebuild_sets();self.rebuild_individual();self.changed()

    def system_selected(self,item,*_):
        if self.loading or not item:return
        self.draft['system']=item.data(Qt.ItemDataRole.UserRole);self.select_sets();self.changed();self.refresh_individual_icons()

    def aftermarket_selected(self,*_):
        if self.loading or not self.aftermarket.currentData():return
        self.draft['system']='theme:'+self.aftermarket.currentData();self.select_sets();self.changed();self.refresh_individual_icons()

    def other_selected(self,item,*_):
        if self.loading or not item:return
        self.draft['other']=item.data(Qt.ItemDataRole.UserRole);self.changed();self.refresh_individual_icons()

    def use_other_system(self):
        self.draft['system']='other';self.select_sets();self.changed();self.refresh_individual_icons();self.tabs.setCurrentIndex(0)

    def rebuild_individual(self):
        selected=self.selected_name();self.individual.clear()
        for name in [*art.CATALOG,*sorted((set(self.draft['overrides'])|self.extra_names)-art.CATALOG.keys())]:
            item=QListWidgetItem();item.setData(Qt.ItemDataRole.UserRole,name);self.individual.addItem(item)
            if name==selected:self.individual.setCurrentItem(item)
        if not self.individual.currentItem() and self.individual.count():self.individual.setCurrentRow(0)
        self.refresh_individual_icons();self.filter_icons()

    def refresh_individual_icons(self):
        for i in range(self.individual.count()):
            item=self.individual.item(i);name=item.data(Qt.ItemDataRole.UserRole)
            item.setText(art.CATALOG.get(name,(name,))[0]+('  ·  Custom' if name in self.draft['overrides'] else ''))
            item.setIcon(QIcon(model.preview_path(self.draft,name,runtime.design(),runtime.mode())));item.setToolTip(name)
        self.single_selected()
        self.filter_icons()

    def filter_icons(self,*_):
        query=self.filter.text().casefold();category=self.category.currentText()
        for i in range(self.individual.count()):
            item=self.individual.item(i);name=item.data(Qt.ItemDataRole.UserRole);group=art.CATALOG.get(name,('','Apps'))[1]
            item.setHidden(query not in (name+' '+item.text()).casefold() or (category not in ('All icons',group) and not (category=='Customized' and name in self.draft['overrides'])))

    def selected_name(self):
        item=self.individual.currentItem() if hasattr(self,'individual') else None
        return item.data(Qt.ItemDataRole.UserRole) if item else ''

    def single_selected(self,*_):
        if not hasattr(self,'reset_button'):return
        name=self.selected_name();self.choose_button.setEnabled(bool(name));self.borrow_button.setEnabled(name in art.CATALOG);self.reset_button.setEnabled(name in self.draft['overrides'])
        self.single_name.setText(art.CATALOG.get(name,(name,))[0]);self.single_image.setPixmap(QIcon(model.preview_path(self.draft,name,runtime.design(),runtime.mode())).pixmap(144,144) if name else QIcon().pixmap(1,1))
        self.single_detail.setText(name+('\nYour individual choice is active in this preview.' if name in self.draft['overrides'] else '\nFollows your selected icon set.'))

    def add_name(self):
        name,ok=QInputDialog.getText(self,'Individual icon','Icon name from the application’s shortcut (for example firefox):')
        if not ok:return
        name=name.strip()
        if not model.ICON.fullmatch(name):self.failed('Use the icon name without spaces, slashes or a file extension.');return
        name=art.ALIASES.get(name,name);self.extra_names.add(name);self.rebuild_individual()
        for i in range(self.individual.count()):
            if self.individual.item(i).data(Qt.ItemDataRole.UserRole)==name:self.individual.setCurrentRow(i);break

    def choose_image(self):
        name=self.selected_name()
        if not name:return
        path,_=QFileDialog.getOpenFileName(self,'Choose individual icon',str(Path.home()/'Pictures'),'Images (*.svg *.png *.webp *.jpg *.jpeg *.ico *.bmp)')
        if path:
            try:self.draft['overrides'][name]=model.import_image(path);self.refresh_individual_icons();self.changed()
            except (OSError,ValueError) as error:self.failed(str(error))

    def borrow(self):
        name=self.selected_name()
        if name not in art.CATALOG:return
        try:
            path=model.ROOT/'icon_themes/packs'/('Xetal-System-'+self.single_set.currentData())/'scalable'/(name+'.svg')
            self.draft['overrides'][name]=model.import_image(path);self.refresh_individual_icons();self.changed()
        except (OSError,ValueError) as error:self.failed(str(error))

    def reset_icon(self):
        self.draft['overrides'].pop(self.selected_name(),None);self.refresh_individual_icons();self.changed()

    def reset_individual(self):
        self.draft['overrides']={};self.refresh_individual_icons();self.changed()

    def import_pack(self):
        path=QFileDialog.getExistingDirectory(self,'Choose extracted icon-set folder',str(Path.home()/'Downloads'))
        if not path:return
        self.busy=True;self.changed();self.status.setText('Importing icon set…')
        self.async_run(lambda:model.import_pack(path),self.imported,self.failed)

    def imported(self,key):
        self.busy=False;self.draft['other']='theme:'+key;self.rebuild_sets();self.changed();self.status.setText('Icon set imported. Preview it here, then Apply icons.');self.tabs.setCurrentIndex(1)

    def changed(self):
        self.dirty=self.draft!=self.baseline or bool(self.load_error);self.tabs.setEnabled(not self.busy);self.reload_button.setEnabled(not self.busy)
        self.discard_button.setEnabled(self.dirty and not self.busy);self.apply_button.setEnabled(self.dirty and not self.busy);self.preview.show_choice(self.draft)
        theme=model.resolve_other(self.draft['other'],runtime.mode());entry=self.available.get(theme,{});self.other_title.setText(entry.get('name',theme))
        self.other_details.setText(entry.get('comment','Application icons and fallback symbols.'))
        for name,label in self.other_images.items():label.setPixmap(QIcon(model.lookup(theme,name,tuple(model.search_paths()))).pixmap(64,64))

    def refresh(self,force=False):
        if self.busy or self.dirty and not force:return
        try:model.ensure();self.baseline,self.token=model.load();self.fill(self.baseline)
        except (OSError,ValueError) as error:self.failed(str(error))

    def save(self):
        self.busy=True;self.changed();self.status.setText('Applying icons…');draft=deepcopy(self.draft)
        self.async_run(lambda:model.save(draft,self.token),self.saved,self.failed)

    def saved(self,result):
        self.baseline,self.token=result;self.busy=False;self.load_error='';model.apply_qt();self.fill(self.baseline);self.status.setText('Saved. Your icon choices are active across Fusion.')

    def failed(self,error):
        self.busy=False;self.changed();self.status.setText(str(error))
