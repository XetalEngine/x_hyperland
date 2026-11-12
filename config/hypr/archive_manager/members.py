"""Paged, disk-backed filesystem view of an archive; no file extraction for browsing."""
from collections import OrderedDict
import json
from pathlib import Path
import sqlite3

from PyQt6.QtCore import QAbstractItemModel, QModelIndex, QMimeDatabase, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QStyle
from file_jobs.model import amount


class MemberModel(QAbstractItemModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.db = None; self.query = ''; self.count = 0
        self.pages = OrderedDict(); self.nodes = OrderedDict(); self.counts = OrderedDict()
        self.sort_column = 't.name COLLATE NOCASE'; self.direction = 'ASC'
        self.mime = QMimeDatabase()

    def clear_cache(self):
        self.pages.clear(); self.nodes.clear(); self.counts.clear()

    @staticmethod
    def cache(cache, key, value, limit):
        cache[key] = value; cache.move_to_end(key)
        if len(cache)>limit: cache.popitem(last=False)
        return value

    def open(self, path):
        self.beginResetModel()
        if self.db: self.db.close()
        self.db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
        self.count = self.db.execute('SELECT COUNT(*) FROM members').fetchone()[0]
        self.query = ''; self.clear_cache(); self.endResetModel()

    def close(self):
        self.beginResetModel()
        if self.db: self.db.close()
        self.db = None; self.count = 0; self.clear_cache(); self.endResetModel()

    def filter(self, text):
        self.beginResetModel(); self.query=text; self.clear_cache()
        if self.db:
            self.db.execute('DROP TABLE IF EXISTS temp.matches')
            if text:
                self.db.execute('CREATE TEMP TABLE matches (id INTEGER PRIMARY KEY)')
                self.db.execute('''INSERT INTO matches WITH RECURSIVE visible(id,parent) AS (
                    SELECT id,parent FROM tree WHERE instr(lower(path),lower(?))>0
                    UNION SELECT t.id,t.parent FROM tree t JOIN visible v ON t.id=v.parent
                    ) SELECT id FROM visible''',(text,))
        self.endResetModel()

    def condition(self):
        return ' AND t.id IN (SELECT id FROM temp.matches)' if self.query else ''

    def ordering(self):
        return f't.directory DESC,{self.sort_column} {self.direction},t.name COLLATE NOCASE,t.id'

    def rowCount(self, parent=QModelIndex()):
        if not self.db or (parent.isValid() and parent.column()!=0): return 0
        ident = parent.internalId() if parent.isValid() else 0
        if ident not in self.counts:
            count = self.db.execute('SELECT COUNT(*) FROM tree t WHERE t.parent=?'+self.condition(),(ident,)).fetchone()[0]
            self.cache(self.counts,ident,count,2048)
        return self.counts[ident]

    def columnCount(self, parent=QModelIndex()): return 5

    def entry(self, row, parent=QModelIndex()):
        ident = parent.internalId() if parent.isValid() else 0
        page = row//256; key = (ident,page)
        if key not in self.pages:
            rows = self.db.execute('SELECT t.id,t.parent,t.path,t.name,t.directory,m.data FROM tree t '
                'LEFT JOIN members m ON m.id=t.member WHERE t.parent=?'+self.condition()+
                ' ORDER BY '+self.ordering()+' LIMIT 256 OFFSET ?',(ident,page*256)).fetchall()
            values=[]
            for offset,(node,owner,path,name,directory,data) in enumerate(rows):
                item=json.loads(data) if data else dict(size=0,packed=0)
                item.update(id=node,parent=owner,path=path,name=name,directory=bool(directory),row=page*256+offset)
                values.append(item); self.cache(self.nodes,node,item,4096)
            self.cache(self.pages,key,values,16)
        self.pages.move_to_end(key)
        return self.pages[key][row%256]

    def node(self, ident):
        if ident not in self.nodes:
            found=self.db.execute('SELECT parent FROM tree WHERE id=?',(ident,)).fetchone()
            if not found: return None
            row=self.db.execute('SELECT position FROM (SELECT t.id,row_number() OVER (ORDER BY '+self.ordering()+')-1 AS position '
                'FROM tree t LEFT JOIN members m ON m.id=t.member WHERE t.parent=?'+self.condition()+') WHERE id=?',(found[0],ident)).fetchone()
            if not row:return None
            parent=self.createIndex(0,0,found[0]) if found[0] else QModelIndex()
            return self.entry(row[0],parent)
        self.nodes.move_to_end(ident)
        return self.nodes[ident]

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row,column,parent): return QModelIndex()
        return self.createIndex(row,column,self.entry(row,parent)['id'])

    def parent(self, index):
        if not index.isValid() or not self.db: return QModelIndex()
        item=self.node(index.internalId())
        parent=self.node(item['parent']) if item and item['parent'] else None
        return self.createIndex(parent['row'],0,parent['id']) if parent else QModelIndex()

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not self.db: return None
        item=self.node(index.internalId())
        if not item:return None
        if role == Qt.ItemDataRole.ToolTipRole: return item['path']
        if role == Qt.ItemDataRole.DecorationRole and index.column()==0:
            fallback=QStyle.StandardPixmap.SP_DirIcon if item['directory'] else QStyle.StandardPixmap.SP_FileIcon
            name='folder' if item['directory'] else self.mime.mimeTypeForFile(item['name'],QMimeDatabase.MatchMode.MatchExtension).iconName()
            return QIcon.fromTheme(name,QApplication.style().standardIcon(fallback))
        if role == Qt.ItemDataRole.DisplayRole:
            return (item['name'],'Folder' if item['directory'] else amount(item['size']),
                '' if item['directory'] else amount(item['packed']),item.get('method') or '',
                'Yes' if item.get('encrypted') else '')[index.column()]
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in (1,2):
            return Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter

    def flags(self, index):
        if not index.isValid():return Qt.ItemFlag.NoItemFlags
        flags=Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|Qt.ItemFlag.ItemIsDragEnabled
        if not self.node(index.internalId())['directory']: flags|=Qt.ItemFlag.ItemNeverHasChildren
        return flags

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole and orientation==Qt.Orientation.Horizontal:
            return ('Name','Size','Packed size','Method','Encrypted')[section]

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if not 0<=column<5:return
        self.beginResetModel()
        self.sort_column=('t.name COLLATE NOCASE','m.size','m.packed',"json_extract(m.data,'$.method')","json_extract(m.data,'$.encrypted')")[column]
        self.direction='DESC' if order==Qt.SortOrder.DescendingOrder else 'ASC'
        self.clear_cache();self.endResetModel()

    def selection(self, indexes):
        rows={index.internalId():self.node(index.internalId()) for index in indexes if index.isValid() and index.column()==0}
        folders={item['path'] for item in rows.values() if item and item['directory']}
        return [item['path'] for item in rows.values() if item and not any(str(p) in folders for p in Path(item['path']).parents)]

    def matching_folders(self):
        if self.db and self.query:
            for (ident,) in self.db.execute('SELECT t.id FROM tree t JOIN temp.matches s ON s.id=t.id WHERE t.directory=1 ORDER BY length(t.path),t.path'):
                item=self.node(ident)
                if item:yield self.createIndex(item['row'],0,ident)
