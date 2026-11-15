import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from clipboard.store import Store,Frames,entry,write_private,MAX_HISTORY,PIN_LIMIT

TEXT='text/plain;charset=utf-8'

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'state/pins.json';self.store=Store(self.path)

    def test_recent_entries_are_only_in_memory_and_deduplicate(self):
        self.store.add(TEXT,b'one');self.store.add(TEXT,b'two');self.store.add(TEXT,b'one')
        self.assertEqual([i.text for i in self.store.items],['one','two'])
        self.assertFalse(self.path.exists());self.assertFalse(Store(self.path).items)

    def test_pin_survives_logout_clear_and_dedup_and_is_private(self):
        self.store.add(TEXT,'é\nhello'.encode());key=self.store.items[0].key;self.store.pin(key)
        self.store.add(TEXT,b'transient');self.store.add(TEXT,'é\nhello'.encode())
        self.assertTrue(self.store.items[0].pinned);self.store.clear()
        self.assertEqual(self.store.items,Store(self.path).items)
        self.assertEqual(self.path.stat().st_mode&0o777,0o600)
        self.assertEqual(self.path.parent.stat().st_mode&0o777,0o700)
        self.store.pin(key);self.assertFalse(Store(self.path).items)

    def test_delete_pinned_item_persists(self):
        self.store.add(TEXT,b'one');key=self.store.items[0].key;self.store.pin(key);self.store.delete(key)
        self.assertEqual(Store(self.path).items,[])

    def test_paused_copies_are_ignored(self):
        self.store.paused=True;self.assertFalse(self.store.add(TEXT,b'paused'));self.assertFalse(self.store.items)

    def test_count_and_byte_limits_preserve_pins(self):
        self.store.add(TEXT,b'pin');key=self.store.items[0].key;self.store.pin(key)
        for index in range(MAX_HISTORY+20):self.store.add(TEXT,str(index).encode())
        self.assertEqual(len(self.store.items),MAX_HISTORY+1)
        self.assertTrue(any(i.key==key for i in self.store.items))
        for index in range(6):self.store.add('image/png',bytes([index])*8*1024*1024)
        self.assertLessEqual(sum(len(i.data) for i in self.store.items),32*1024*1024)
        self.assertTrue(any(i.key==key for i in self.store.items))

    def test_pin_limit_has_no_partial_effect(self):
        for index in range(25):self.store.add(TEXT,str(index).encode());self.store.pin(self.store.items[0].key)
        self.store.add(TEXT,b'excess');before=self.path.read_bytes()
        with self.assertRaises(ValueError):self.store.pin(self.store.items[0].key)
        self.assertFalse(self.store.items[0].pinned);self.assertEqual(self.path.read_bytes(),before)

    def test_save_failure_does_not_lose_pin(self):
        self.store.add(TEXT,b'keep');key=self.store.items[0].key;self.store.pin(key)
        with patch('clipboard.store.write_private',side_effect=OSError('test')):
            with self.assertRaises(OSError):self.store.delete(key)
        self.assertEqual(len(self.store.items),1);self.assertTrue(self.store.items[0].pinned)

    def test_reject_unsupported_binary_and_oversized_text(self):
        for mime,data in [('text/uri-list',b'file:///test'),(TEXT,b'\xff'),(TEXT,b'abc\0'),(TEXT,b' '),(TEXT,b'x'*(1024*1024+1))]:
            with self.assertRaises(ValueError):self.store.add(mime,data)
        self.assertFalse(self.store.items)

    def test_invalid_pin_file_is_not_destroyed(self):
        self.path.parent.mkdir();self.path.write_bytes(b'bad json')
        with self.assertRaises(ValueError):Store(self.path)
        self.assertEqual(self.path.read_bytes(),b'bad json')

class StreamTests(unittest.TestCase):
    def test_arbitrary_fragment_boundaries_and_multiple_frames(self):
        payload='a\né🍀'.encode();wire=f'{TEXT} {len(payload)}\n'.encode()+payload+b'image/png 4\n\0\n\xff\r'
        for size in (1,2,7,len(wire)):
            frames=Frames();found=[]
            for offset in range(0,len(wire),size):found+=frames.feed(wire[offset:offset+size])
            self.assertEqual(found,[(TEXT,payload),('image/png',b'\0\n\xff\r')])

    def test_bad_length_and_mime_are_rejected_before_buffering(self):
        for data in (b'text/html 2\nxx',b'image/png 999999999\n',b'image/png -1\n',b'image/png 0\n',b'x'*129):
            with self.assertRaises(ValueError):Frames().feed(data)

    def test_sensitive_and_file_offers_are_never_selected(self):
        source='''#include "formats.hpp"
#include <cassert>
int main(){using Clipboard::choose;
assert(choose({"text/html","text/plain"})=="text/plain");
assert(choose({"text/plain","image/png"})=="image/png");
for(auto mime:{"text/uri-list","x-special/gnome-copied-files","application/x-kde-cutselection","x-kde-passwordManagerHint","application/x-keepassxc"})
 assert(choose({"text/plain","image/png",mime}).empty());
assert(choose({"text/html"}).empty());}
'''
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'formats.cpp';path.write_text(source);binary=path.with_suffix('')
            subprocess.run(['c++','-std=c++20','-I'+str(ROOT/'clipboard/native'),str(path),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True)

if __name__=='__main__':unittest.main()
