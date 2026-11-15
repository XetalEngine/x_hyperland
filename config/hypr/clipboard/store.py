"""Bounded clipboard history. Only explicitly pinned entries survive logout."""
from __future__ import annotations
from dataclasses import dataclass
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile

MIMES={'text/plain;charset=utf-8','image/png','image/jpeg','image/webp'}
TEXT_LIMIT=1024*1024
ITEM_LIMIT=8*1024*1024
HISTORY_LIMIT=32*1024*1024
PIN_LIMIT=16*1024*1024
MAX_HISTORY=100
MAX_PINS=25

@dataclass(frozen=True)
class Entry:
    mime: str
    data: bytes
    key: str
    pinned: bool=False

    @property
    def text(self):return self.data.decode('utf-8') if self.mime.startswith('text/') else ''

def entry(mime,data,pinned=False):
    if mime not in MIMES or not data or len(data)>(TEXT_LIMIT if mime.startswith('text/') else ITEM_LIMIT):
        raise ValueError('Unsupported clipboard item or item too large.')
    if mime.startswith('text/'):
        text=data.decode('utf-8')
        if '\0' in text or not text.strip():raise ValueError('Empty or non-text clipboard item.')
    return Entry(mime,data,hashlib.sha256(mime.encode()+b'\0'+data).hexdigest(),pinned)

def write_private(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,name=tempfile.mkstemp(dir=path.parent,prefix='.'+path.name+'-')
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(value,stream,ensure_ascii=False); stream.flush(); os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

class Store:
    def __init__(self,path: Path,*,load=True):
        self.path=path; self.items=[]; self.paused=False; self.pins_unavailable=False
        if load:self.load()

    def load(self):
        try:
            if self.path.stat().st_size>PIN_LIMIT*2:raise ValueError('Pinned history is too large.')
            value=json.loads(self.path.read_text())
        except FileNotFoundError:return
        if not isinstance(value,dict) or value.get('version')!=1 or not isinstance(value.get('items'),list):
            raise ValueError('Invalid pinned clipboard history.')
        items=[]; keys=set()
        for saved in value['items']:
            item=entry(saved['mime'],base64.b64decode(saved['data'],validate=True),True)
            if item.key not in keys:items.append(item); keys.add(item.key)
        if len(items)>MAX_PINS or sum(len(i.data) for i in items)>PIN_LIMIT:raise ValueError('Pinned history is too large.')
        self.items=items

    def save(self,items):
        if self.pins_unavailable:raise ValueError('Saved pins could not be read; leaving them untouched.')
        write_private(self.path,{'version':1,'items':[{'mime':i.mime,'data':base64.b64encode(i.data).decode('ascii')} for i in items if i.pinned]})

    def trim(self):
        while (sum(not i.pinned for i in self.items)>MAX_HISTORY or sum(len(i.data) for i in self.items)>HISTORY_LIMIT):
            index=next((n for n in range(len(self.items)-1,-1,-1) if not self.items[n].pinned),None)
            if index is None:break
            self.items.pop(index)

    def add(self,mime,data):
        if self.paused:return False
        item=entry(mime,data)
        previous=next((i for i in self.items if i.key==item.key),None)
        if previous:item=previous
        if self.items and self.items[0].key==item.key:return False
        self.items=[item,*[i for i in self.items if i.key!=item.key]]; self.trim(); return True

    def pin(self,key):
        item=next((i for i in self.items if i.key==key),None)
        if item is None:return
        if not item.pinned:
            pins=[i for i in self.items if i.pinned]
            if len(pins)>=MAX_PINS or sum(len(i.data) for i in pins)+len(item.data)>PIN_LIMIT:
                raise ValueError('Pinned history is full (25 items / 16 MiB). Unpin an item first.')
        items=[Entry(i.mime,i.data,i.key,not i.pinned) if i.key==key else i for i in self.items]
        self.save(items); self.items=items; self.trim()

    def delete(self,key):
        items=[i for i in self.items if i.key!=key]
        if any(i.key==key and i.pinned for i in self.items):self.save(items)
        self.items=items

    def clear(self):self.items=[i for i in self.items if i.pinned]

class Frames:
    """Collector frames may arrive split anywhere, including inside UTF-8."""
    def __init__(self):self.buffer=bytearray(); self.header=None
    def feed(self,data):
        self.buffer.extend(data); result=[]
        while True:
            if self.header is None:
                end=self.buffer.find(b'\n')
                if end<0:
                    if len(self.buffer)>128:raise ValueError('Invalid clipboard stream.')
                    break
                if end>128:raise ValueError('Invalid clipboard stream.')
                mime,count=bytes(self.buffer[:end]).decode('ascii').split(' ')
                size=int(count)
                if mime not in MIMES or size<1 or size>(TEXT_LIMIT if mime.startswith('text/') else ITEM_LIMIT):
                    raise ValueError('Invalid clipboard stream.')
                del self.buffer[:end+1]; self.header=(mime,size)
            mime,size=self.header
            if len(self.buffer)<size:break
            result.append((mime,bytes(self.buffer[:size]))); del self.buffer[:size]; self.header=None
        return result
