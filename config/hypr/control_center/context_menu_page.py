"""Draft-based desktop menu editor with a non-executing live preview."""
import copy
from pathlib import Path
import sys
import uuid

from PyQt6.QtCore import Qt, QTimer, QFileSystemWatcher, QRectF, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QLinearGradient, QPen
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView, QSplitter, QTabWidget, QScrollArea,
    QFormLayout, QLineEdit, QComboBox, QCheckBox, QSpinBox, QColorDialog, QFileDialog,
    QMessageBox, QMenu, QDialog, QListWidget, QListWidgetItem, QDialogButtonBox)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'desktop_menu'))
import menu_config
import menu_hotkeys
import appearance

STYLE = '''
QTreeWidget {background:#10151c; alternate-background-color:#1b222c; border:1px solid #364251; padding:4px; outline:0;}
QTreeWidget::item {padding:8px 3px; border-radius:4px;}
QTreeWidget::item:selected {background:#284855; color:#ecfffb;}
QSpinBox {background:#10151c; border:1px solid #364251; padding:6px; min-width:65px;}
QFrame#menuPreview {background:#101820; border:1px solid #344655; border-radius:10px;}
'''


def icon(value):
    return QIcon(str(Path(value).expanduser())) if value.startswith(('/', '~')) else QIcon.fromTheme(value)


def button(text, callback, primary=False):
    widget = QPushButton(text); widget.clicked.connect(callback)
    if primary: widget.setObjectName('primary')
    return widget


class ItemTree(QTreeWidget):
    reordered = pyqtSignal()
    def dropEvent(self, event):
        super().dropEvent(event)
        self.reordered.emit()


class MenuPreview(QWidget):
    selected = pyqtSignal(str)
    def __init__(self):
        super().__init__(); self.setMinimumSize(240, 250)
        self.config = menu_config.defaults(); self.items = self.config['items']
        self.hotkeys = {}; self.boxes = []; self.chosen = ''

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#101820'))
        style = self.config['style']; colors = appearance.colors(style)
        columns = appearance.columns(self.items)
        if not columns:
            p.setPen(QColor(colors['text'])); p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Add a shortcut to preview your menu')
            return
        inset = style['padding']; accent = style['accent_width']; gap = 13
        width = len(columns)*style['width'] + (len(columns)-1)*gap + 2*inset + accent
        heights = appearance.row_heights(columns, style)
        height = sum(heights)+2*inset+2
        scale = min(1., (self.width()-24)/width, (self.height()-24)/height)
        left = (self.width()-width*scale)/2; top = min(24, max(12, (self.height()-height*scale)/2))
        p.translate(left, top); p.scale(scale, scale)
        self.boxes = []
        body = QRectF(0, 0, width, height)
        path = QPainterPath(); path.addRoundedRect(body, style['rounding'], style['rounding'])
        gradient = QLinearGradient(body.topLeft(), body.bottomRight())
        for pos, key in ((0, 'background'), (1, 'background_end')):
            c = QColor(colors[key]); c.setAlphaF(style['opacity']/100); gradient.setColorAt(pos, c)
        p.setClipPath(path); p.fillPath(path, gradient)
        p.fillRect(QRectF(0, 0, accent, height), QColor(colors['accent']))
        p.setClipping(False); p.setPen(QPen(QColor(colors['border']), 1)); p.drawPath(path)
        font = QFont(style['font_family']); font.setPixelSize(style['font_size']); p.setFont(font)
        for col, entries in enumerate(columns):
            x = accent+inset+col*(style['width']+gap); y = inset+1
            if col:
                p.setPen(QColor(colors['divider'])); p.drawLine(int(x-7), inset+5, int(x-7), int(height-inset-5))
            for index, item in enumerate(entries):
                h = heights[index]; rect = QRectF(x, y, style['width'], h)
                self.boxes.append((QRectF(left+x*scale, top+y*scale, rect.width()*scale, h*scale), item['id']))
                kind = item['kind']
                if kind == 'separator':
                    p.setPen(QColor(colors['divider'])); p.drawLine(int(x+12), int(y+h/2), int(rect.right()-12), int(y+h/2))
                elif kind != 'spacer':
                    if self.chosen == item['id']:
                        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(colors['hover'])); p.drawRoundedRect(rect, 7, 7)
                    tx = x+12; room = style['width']-24
                    if style['show_icons'] and kind != 'heading':
                        size = style['icon_size']; icon(item['icon']).paint(p, int(tx), int(y+(h-size)/2), size, size)
                        tx += size+12; room -= size+12
                    p.setPen(QColor(colors['accent'] if kind == 'heading' else colors['text']))
                    font.setBold(kind == 'heading'); p.setFont(font)
                    hint = '›' if kind == 'submenu' else (self.hotkeys.get(item['id'], [''])[0] if style['show_hotkeys'] else '')
                    if hint:
                        space = min(room/2, p.fontMetrics().horizontalAdvance(hint)+14)
                        p.drawText(QRectF(rect.right()-12-space, y, space, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                                   p.fontMetrics().elidedText(hint, Qt.TextElideMode.ElideRight, int(space)))
                        room -= space+8
                    p.drawText(QRectF(tx, y, max(0, room), h), Qt.AlignmentFlag.AlignVCenter,
                               p.fontMetrics().elidedText(item['label'], Qt.TextElideMode.ElideRight, max(0, int(room))))
                y += h

    def mousePressEvent(self, event):
        for rect, ident in self.boxes:
            if rect.contains(event.position()): self.selected.emit(ident); break


class ApplicationPicker(QDialog):
    def __init__(self, parent):
        super().__init__(parent); self.setWindowTitle('Add application'); self.resize(600, 540); self.entry = None
        sys.path.insert(0, str(ROOT/'launcher'))
        import catalog
        self.entries = sorted(catalog.applications().values(), key=lambda entry: entry.get_display_name().casefold())
        layout = QVBoxLayout(self); self.search = QLineEdit(); self.search.setPlaceholderText('Search applications and saved shortcuts…')
        layout.addWidget(self.search); self.list = QListWidget(); self.list.setIconSize(QSize(28,28)); layout.addWidget(self.list,1)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(self.choose); controls.rejected.connect(self.reject); layout.addWidget(controls)
        self.list.itemDoubleClicked.connect(self.choose); self.search.textChanged.connect(self.populate); self.populate()

    def populate(self):
        self.list.clear(); query = self.search.text().casefold()
        for entry in self.entries:
            if query in (entry.get_display_name()+' '+entry.get_id()).casefold():
                row = QListWidgetItem(icon(entry.fields['icon']), entry.get_display_name())
                row.setData(Qt.ItemDataRole.UserRole, entry); self.list.addItem(row)
        if self.list.count(): self.list.setCurrentRow(0)

    def choose(self, *_):
        if self.list.currentItem():
            self.entry = self.list.currentItem().data(Qt.ItemDataRole.UserRole); self.accept()


class ContextMenuPage(QWidget):
    def __init__(self, async_run, store=None):
        super().__init__(); self.async_run = async_run; self.store = store or menu_config.Store()
        self.loading = False; self.busy = False; self.dirty = False; self.expected = None
        self.baseline = menu_config.defaults(); self.draft = copy.deepcopy(self.baseline); self.current = None
        self.hotkeys = {}; self.inputs = {}; self.style_inputs = {}; self.color_buttons = {}
        root = QVBoxLayout(self); root.setContentsMargins(18,16,18,16); root.setSpacing(10)
        top = QHBoxLayout(); title = QLabel('Your desktop, your menu'); title.setObjectName('brand'); top.addWidget(title); top.addStretch()
        self.enabled = QCheckBox('Enable desktop menu'); self.enabled.toggled.connect(self.edit_enabled); top.addWidget(self.enabled); root.addLayout(top)
        subtitle = QLabel('Arrange shortcuts and sections. Preview changes here, then Apply to update your desktop.'); subtitle.setObjectName('muted'); root.addWidget(subtitle)
        tools = QHBoxLayout(); add = QPushButton('+ Add'); menu = QMenu(add)
        menu.addAction('Application…', self.add_application)
        for kind, label in menu_config.KINDS.items(): menu.addAction(label, lambda checked=False, k=kind: self.add_item(k))
        add.setMenu(menu); tools.addWidget(add)
        tools.addWidget(button('↑', lambda: self.move_item(-1))); tools.addWidget(button('↓', lambda: self.move_item(1)))
        tools.addWidget(button('Duplicate', self.duplicate)); tools.addWidget(button('Remove…', self.remove)); tools.addStretch()
        tools.addWidget(button('Reset defaults', self.reset_defaults)); tools.addWidget(button('Save preset…', self.save_preset)); tools.addWidget(button('Load preset…', self.load_preset)); root.addLayout(tools)
        split = QSplitter(); root.addWidget(split,1)
        self.tree = ItemTree(); self.tree.setHeaderLabels(['Menu items']); self.tree.setMinimumWidth(200)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove); self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection); self.tree.setAlternatingRowColors(True)
        self.tree.currentItemChanged.connect(self.select); self.tree.itemChanged.connect(self.item_checked); self.tree.reordered.connect(self.read_tree); split.addWidget(self.tree)
        self.properties = QTabWidget(); split.addWidget(self.properties)
        self.item_widget, form = self.form_tab('Item')
        self.form = form
        self.type_label = QLabel(); form.addRow('Type', self.type_label)
        self.add_text('label','Name'); self.add_text('icon','Icon', self.choose_icon)
        self.target = QComboBox()
        for value, label in menu_config.TARGETS.items(): self.target.addItem(label, value)
        self.target.currentIndexChanged.connect(self.edit_item); form.addRow('Action',self.target)
        self.add_text('value','Destination', self.browse_value); self.add_text('directory','Working folder',self.browse_directory)
        self.inputs['value'].setPlaceholderText('Command, application ID, folder or https:// address')
        for name, label in [('terminal','Run in Kitty'),('hold','Keep terminal open'),('shell','Use shell syntax (pipes, &&, variables)')]:
            w=QCheckBox(label); w.toggled.connect(self.edit_item); form.addRow(w); self.inputs[name]=w
        self.space = QSpinBox(); self.space.setRange(2,96); self.space.setSuffix(' px'); self.space.valueChanged.connect(self.edit_item); form.addRow('Spacer height',self.space)
        self.hotkey = QLabel(); self.hotkey.setWordWrap(True); form.addRow('Global hotkey',self.hotkey)
        self.hotkey_button = button('Configure hotkey…',self.configure_hotkey); form.addRow(self.hotkey_button)
        self.item_tip = QLabel('Global hotkeys also appear in Hotkeys → Applications. Apply menu edits before assigning one.'); self.item_tip.setObjectName('muted'); self.item_tip.setWordWrap(True); form.addRow(self.item_tip)
        _, form = self.form_tab('Appearance')
        self.palette = QComboBox(); self.palette.addItem('Follow system theme','system'); self.palette.addItem('Custom colors','custom')
        self.palette.currentIndexChanged.connect(self.edit_style); form.addRow('Palette',self.palette)
        labels={'width':'Column width','row_height':'Row height','icon_size':'Icon size','font_size':'Font size','padding':'Menu padding','rounding':'Corner radius','accent_width':'Left accent strip','opacity':'Opacity'}
        for key,(low,high) in menu_config.LIMITS.items():
            w=QSpinBox(); w.setRange(low,high); w.setSuffix(' %' if key=='opacity' else ' px'); w.valueChanged.connect(self.edit_style)
            self.style_inputs[key]=w; form.addRow(labels[key],w)
        self.font = QLineEdit(); self.font.textEdited.connect(self.edit_style); form.addRow('Font family',self.font)
        for key,label in [('show_icons','Show icons'),('show_hotkeys','Show hotkeys'),('shadow','Menu shadow')]:
            w=QCheckBox(label); w.toggled.connect(self.edit_style); self.style_inputs[key]=w; form.addRow(w)
        for key in menu_config.CUSTOM_COLORS:
            w=button('Choose…',lambda checked=False,k=key:self.choose_color(k)); self.color_buttons[key]=w
            form.addRow(key.replace('_',' ').title(),w)
        preview_area=QWidget(); preview_layout=QVBoxLayout(preview_area); preview_layout.setContentsMargins(8,0,0,0)
        self.preview_title=QLabel('Preview'); self.preview_title.setObjectName('eyebrow'); preview_layout.addWidget(self.preview_title)
        self.preview=MenuPreview(); self.preview.selected.connect(self.select_id); preview_layout.addWidget(self.preview,1)
        hint=QLabel('Click an item to edit it. Submenus preview when selected.'); hint.setObjectName('muted'); hint.setWordWrap(True); preview_layout.addWidget(hint); split.addWidget(preview_area)
        split.setSizes([255,410,345]); split.setChildrenCollapsible(False)
        bottom=QHBoxLayout(); self.status=QLabel(); self.status.setObjectName('status'); self.status.setWordWrap(True); bottom.addWidget(self.status,1)
        bottom.addWidget(button('Reload',self.reload_clicked)); self.discard=button('Discard',self.discard_changes); bottom.addWidget(self.discard)
        self.apply_button=button('Apply changes',self.apply,True); bottom.addWidget(self.apply_button); root.addLayout(bottom)
        self.watcher=QFileSystemWatcher([str(self.store.path.parent)],self)
        self.delay=QTimer(self); self.delay.setSingleShot(True); self.delay.setInterval(200); self.delay.timeout.connect(self.external_change)
        self.watcher.directoryChanged.connect(lambda _:self.delay.start())
        self.refresh()

    def form_tab(self, name):
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        widget=QWidget(); form=QFormLayout(widget); form.setContentsMargins(14,14,14,14); form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        scroll.setWidget(widget); self.properties.addTab(scroll,name); return widget,form

    def add_text(self,key,label,browse=None):
        field=QLineEdit(); field.textEdited.connect(self.edit_item); self.inputs[key]=field
        if browse:
            row=QWidget(); line=QHBoxLayout(row); line.setContentsMargins(0,0,0,0); line.addWidget(field,1); line.addWidget(button('…',browse)); self.form.addRow(label,row)
            field.row_widget=row
        else: self.form.addRow(label,field)

    def render(self, selected=None):
        self.loading=True; self.tree.clear(); self.enabled.setChecked(self.draft['enabled'])
        def fill(parent,items):
            for item in items:
                node=QTreeWidgetItem(parent,[item['label'] if item['kind'] in ('action','submenu','heading') else menu_config.KINDS[item['kind']]])
                node.setData(0,Qt.ItemDataRole.UserRole,item); node.setToolTip(0,menu_config.KINDS[item['kind']])
                flags=node.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled
                if item['kind']!='submenu': flags &= ~Qt.ItemFlag.ItemIsDropEnabled
                node.setFlags(flags); node.setCheckState(0,Qt.CheckState.Checked if item['enabled'] else Qt.CheckState.Unchecked)
                if item['kind'] in ('action','submenu'): node.setIcon(0,icon(item['icon']))
                fill(node,item['children']); node.setExpanded(True)
        fill(self.tree.invisibleRootItem(),self.draft['items'])
        style=self.draft['style']
        for key,widget in self.style_inputs.items():
            widget.setChecked(style[key]) if isinstance(widget,QCheckBox) else widget.setValue(style[key])
        self.font.setText(style['font_family']); self.palette.setCurrentIndex(self.palette.findData(style['palette']))
        self.loading=False; self.select_id(selected or (self.draft['items'][0]['id'] if self.draft['items'] else ''))
        if not self.tree.currentItem(): self.select(None)
        self.changed()

    def select_id(self, ident):
        def visit(parent):
            for n in range(parent.childCount()):
                node=parent.child(n)
                if node.data(0,Qt.ItemDataRole.UserRole)['id']==ident: self.tree.setCurrentItem(node); return True
                if visit(node): return True
            return False
        visit(self.tree.invisibleRootItem())

    def select(self,node,*_):
        if self.loading: return
        self.loading=True; self.current=node.data(0,Qt.ItemDataRole.UserRole) if node else None
        self.item_widget.setEnabled(bool(self.current))
        if self.current:
            item=self.current; self.type_label.setText(menu_config.KINDS[item['kind']])
            for key,w in self.inputs.items():
                w.setChecked(item[key]) if isinstance(w,QCheckBox) else w.setText(item[key])
            self.target.setCurrentIndex(self.target.findData(item['target'])); self.space.setValue(item['height'])
            self.update_item_visibility()
        self.loading=False; self.update_preview(); self.update_hotkey()

    def update_item_visibility(self):
        item=self.current; kind=item['kind']; action=kind=='action'; target=item['target']
        rows=[(self.inputs['label'],kind in ('action','heading','submenu')),(self.inputs['icon'].row_widget,kind in ('action','submenu')),
              (self.target,action),(self.inputs['value'].row_widget,action and target in ('command','application','folder','url')),
              (self.inputs['directory'].row_widget,action and target=='command'),(self.space,kind=='spacer'),
              (self.hotkey,action),(self.hotkey_button,action),(self.item_tip,action)]
        rows.extend((self.inputs[key],action and target=='command') for key in ('terminal','hold','shell'))
        for widget,visible in rows: self.form.setRowVisible(widget,visible)
        self.inputs['hold'].setEnabled(item['terminal'])

    def read_tree(self):
        if self.loading:return
        def collect(parent):
            result=[]
            for n in range(parent.childCount()):
                node=parent.child(n); item=node.data(0,Qt.ItemDataRole.UserRole)
                item['children']=collect(node); node.setData(0,Qt.ItemDataRole.UserRole,item); result.append(item)
            return result
        self.loading=True; self.draft['items']=collect(self.tree.invisibleRootItem()); self.loading=False; self.changed()

    def edit_item(self,*_):
        if self.loading or not self.current:return
        for key,w in self.inputs.items(): self.current[key]=w.isChecked() if isinstance(w,QCheckBox) else w.text()
        self.current['target']=self.target.currentData(); self.current['height']=self.space.value()
        node=self.tree.currentItem(); self.loading=True; node.setData(0,Qt.ItemDataRole.UserRole,self.current)
        node.setText(0,self.current['label'] if self.current['kind'] in ('action','submenu','heading') else menu_config.KINDS[self.current['kind']]); node.setIcon(0,icon(self.current['icon']))
        self.loading=False; self.update_item_visibility(); self.read_tree(); self.update_hotkey()

    def item_checked(self,node,column):
        if self.loading:return
        item=node.data(0,Qt.ItemDataRole.UserRole); item['enabled']=node.checkState(0)==Qt.CheckState.Checked
        self.loading=True; node.setData(0,Qt.ItemDataRole.UserRole,item); self.loading=False; self.read_tree(); self.select(node)

    def edit_enabled(self,value):
        if self.loading:return
        self.draft['enabled']=value; self.changed()

    def edit_style(self,*_):
        if self.loading:return
        for key,w in self.style_inputs.items(): self.draft['style'][key]=w.isChecked() if isinstance(w,QCheckBox) else w.value()
        self.draft['style']['font_family']=self.font.text(); self.draft['style']['palette']=self.palette.currentData(); self.changed()

    def choose_color(self,key):
        selected=QColorDialog.getColor(QColor(self.draft['style'][key]),self,'Choose '+key.replace('_',' ')+' color')
        if selected.isValid(): self.draft['style'][key]=selected.name(); self.changed()

    def choose_icon(self):
        sys.path.insert(0,str(ROOT/'launcher')); from editor import IconPicker
        picker=IconPicker(self.inputs['icon'].text(),self)
        if picker.exec(): self.inputs['icon'].setText(picker.value); self.edit_item()

    def browse_value(self):
        target=self.target.currentData()
        if target=='application':
            picker=ApplicationPicker(self)
            if picker.exec():
                self.inputs['value'].setText(picker.entry.get_id()); self.inputs['label'].setText(picker.entry.get_display_name()); self.inputs['icon'].setText(picker.entry.fields['icon']); self.edit_item()
            return
        if target=='folder': value=QFileDialog.getExistingDirectory(self,'Choose folder',str(Path.home()),options=QFileDialog.Option.DontUseNativeDialog)
        elif target=='command':
            value,_=QFileDialog.getOpenFileName(self,'Choose program',str(Path.home()),options=QFileDialog.Option.DontUseNativeDialog)
            if value:
                import shlex; value=shlex.quote(value)
        else:return
        if value:self.inputs['value'].setText(value);self.edit_item()

    def browse_directory(self):
        value=QFileDialog.getExistingDirectory(self,'Choose working folder',str(Path.home()),options=QFileDialog.Option.DontUseNativeDialog)
        if value:self.inputs['directory'].setText(value);self.edit_item()

    def insertion(self):
        node=self.tree.currentItem()
        if node and node.data(0,Qt.ItemDataRole.UserRole)['kind']=='submenu':return node.childCount(),node
        parent=node.parent() if node else None
        holder=parent or self.tree.invisibleRootItem()
        return (holder.indexOfChild(node)+1 if node else holder.childCount()),holder

    def insert(self,item):
        index,parent=self.insertion(); parent_id=parent.data(0,Qt.ItemDataRole.UserRole)['id'] if parent!=self.tree.invisibleRootItem() else None
        target=menu_config.find(self.draft,parent_id)['children'] if parent_id else self.draft['items']
        target.insert(index,item); self.render(item['id'])

    def add_item(self,kind):
        self.insert(menu_config.new_item(kind,icon='folder' if kind=='submenu' else 'application-x-executable'))

    def add_application(self):
        picker=ApplicationPicker(self)
        if picker.exec(): self.insert(menu_config.new_item(label=picker.entry.get_display_name(),icon=picker.entry.fields['icon'],target='application',value=picker.entry.get_id()))

    def duplicate(self):
        if not self.current:return
        item=copy.deepcopy(self.current)
        for child,_ in menu_config.walk([item]): child['id']=uuid.uuid4().hex
        item['label']+=' (copy)'
        node=self.tree.currentItem(); parent=node.parent() or self.tree.invisibleRootItem(); index=parent.indexOfChild(node)
        source=menu_config.find(self.draft,parent.data(0,Qt.ItemDataRole.UserRole)['id'])['children'] if node.parent() else self.draft['items']
        source.insert(index+1,item); self.render(item['id'])

    def move_item(self,direction):
        node=self.tree.currentItem()
        if not node:return
        parent=node.parent() or self.tree.invisibleRootItem(); index=parent.indexOfChild(node); destination=index+direction
        if not 0<=destination<parent.childCount():return
        self.loading=True; taken=parent.takeChild(index); parent.insertChild(destination,taken); self.tree.setCurrentItem(taken); self.loading=False; self.read_tree(); self.select(taken)

    def remove(self):
        node=self.tree.currentItem()
        if not node:return
        if QMessageBox.question(self,'Remove menu item?','Remove this item and anything inside it?\nAssigned global hotkeys will also be removed when you Apply.',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
        parent=node.parent() or self.tree.invisibleRootItem(); parent.takeChild(parent.indexOfChild(node)); self.read_tree(); self.select(self.tree.currentItem())

    def update_preview(self):
        items=self.draft['items']; name='Preview'; node=self.tree.currentItem()
        if node:
            item=node.data(0,Qt.ItemDataRole.UserRole)
            if item['kind']=='submenu': items=item['children']; name=item['label']
            elif node.parent(): item=node.parent().data(0,Qt.ItemDataRole.UserRole); items=item['children']; name=item['label']
        self.preview.config=self.draft; self.preview.items=items; self.preview.hotkeys=self.hotkeys
        self.preview.chosen=self.current['id'] if self.current else ''; self.preview.update(); self.preview_title.setText(name)

    def update_hotkey(self):
        self.hotkey.setText(' / '.join(self.hotkeys.get(self.current['id'],[])) or 'Not assigned' if self.current else '')
        self.hotkey_button.setEnabled(bool(self.current and self.current['kind']=='action' and not self.dirty and self.expected))

    def configure_hotkey(self):
        if self.dirty or not self.current:return
        sys.path.insert(0,str(ROOT/'launcher')); from hotkey_dialog import HotkeyDialog
        dialog=HotkeyDialog(menu_hotkeys.Entry(self.current),self,adapter=menu_hotkeys); dialog.exec(); self.refresh_hotkeys(); self.update_hotkey(); self.update_preview()

    def refresh_hotkeys(self):
        try:self.hotkeys=menu_hotkeys.labels()
        except Exception:self.hotkeys={}

    def changed(self):
        self.dirty=self.draft!=self.baseline; problem=''
        try:menu_config.validate(self.draft)
        except ValueError as error:problem=str(error)
        self.apply_button.setEnabled(self.dirty and not self.busy and not problem and self.expected is not None)
        self.discard.setEnabled(self.dirty and not self.busy)
        self.status.setText(problem or ('Unsaved changes · Preview only' if self.dirty else 'Right-click the wallpaper to use your menu.'))
        for key,w in self.color_buttons.items():
            w.setText(self.draft['style'][key]); w.setStyleSheet('border-left:8px solid '+self.draft['style'][key]+';')
            w.setEnabled(self.draft['style']['palette']=='custom')
        self.update_preview(); self.update_hotkey()

    def refresh(self):
        if self.busy or self.dirty:return
        try:
            self.baseline,self.expected=self.store.load(); self.draft=copy.deepcopy(self.baseline)
            self.refresh_hotkeys(); self.render()
        except Exception as error:self.status.setText(str(error)); self.apply_button.setEnabled(False)

    def external_change(self):
        if self.busy:return
        try:
            _,expected=self.store.load()
            if expected==self.expected:return
            if self.dirty:self.status.setText('The menu changed elsewhere. Your draft is kept; Reload to use the saved version.')
            else:self.refresh()
        except Exception as error:self.status.setText(str(error))

    def confirm_replace(self):
        return not self.dirty or QMessageBox.question(self,'Replace pending menu edits?','Replace your unapplied menu changes?',QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Discard

    def reload_clicked(self):
        if self.confirm_replace():self.discard_changes()

    def discard_changes(self):
        self.dirty=False; self.refresh()

    def reset_defaults(self):
        if QMessageBox.question(self,'Reset desktop menu?','Load the three original shortcuts and default appearance as a draft?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Yes:
            self.draft=menu_config.defaults(); self.render()

    def save_preset(self):
        path,_=QFileDialog.getSaveFileName(self,'Save context menu preset',str(Path.home()/'Xetal-context-menu.json'),'Menu presets (*.json)',options=QFileDialog.Option.DontUseNativeDialog)
        if path:
            try:self.store.export(path,self.draft);self.status.setText('Preset saved. Pending edits remain unapplied.')
            except Exception as error:self.status.setText(str(error))

    def load_preset(self):
        path,_=QFileDialog.getOpenFileName(self,'Load context menu preset',str(Path.home()),'Menu presets (*.json)',options=QFileDialog.Option.DontUseNativeDialog)
        if path:
            try:
                draft=menu_config.read_preset(path)
                if self.confirm_replace():self.draft=draft;self.render()
            except Exception as error:self.status.setText(str(error))

    def apply(self):
        if not self.apply_button.isEnabled():return
        self.busy=True; self.setEnabled(False); self.status.setText('Saving your desktop menu…')
        draft=copy.deepcopy(self.draft); expected=self.expected
        self.async_run(lambda:menu_hotkeys.save_menu(self.store,draft,expected),self.saved,self.failed)

    def saved(self,expected):
        self.busy=False; self.setEnabled(True); self.dirty=False; self.refresh(); self.status.setText('Applied. Right-click the wallpaper to see your menu.')

    def failed(self,message):
        self.busy=False; self.setEnabled(True); self.changed(); self.status.setText(message)
