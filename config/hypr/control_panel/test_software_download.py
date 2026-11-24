"""Exercise byte integrity and cancellation with disposable files only."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest

from software_download import download, OfficialRedirect


class Response(io.BytesIO):
    def geturl(self): return 'https://www.xetal.net/community/site/Downloads/xmusic/example.run'


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.destination = Path(self.directory.name)/'Music installer.run'
        self.data = b'#!/bin/sh\nexit 0\n__PAYLOAD__\x00\xff\x80'
        self.artifact = dict(url=Response().geturl(), size=len(self.data), sha256=hashlib.sha256(self.data).hexdigest())

    def fetch(self, data=None, **kwargs):
        return download(self.artifact, self.destination,
                        opener=lambda request,timeout: Response(self.data if data is None else data), **kwargs)

    def test_script_is_saved_as_exact_bytes_not_executed_or_made_executable(self):
        progress = []
        self.assertEqual(self.fetch(progress=lambda *value: progress.append(value)), self.destination)
        self.assertEqual(self.destination.read_bytes(), self.data)
        self.assertFalse(self.destination.stat().st_mode & 0o111)
        self.assertEqual(progress[-1], (len(self.data),len(self.data)))
        self.assertEqual(list(self.destination.parent.iterdir()), [self.destination])

    def test_hash_mismatch_short_download_and_extra_data_preserve_existing_file(self):
        for data in (b'x'*len(self.data), self.data[:-1], self.data+b'extra'):
            with self.subTest(data=data):
                self.destination.write_bytes(b'previous download')
                with self.assertRaises(RuntimeError): self.fetch(data)
                self.assertEqual(self.destination.read_bytes(), b'previous download')
                self.assertEqual(list(self.destination.parent.iterdir()), [self.destination])

    def test_cancel_discards_partial_file_and_preserves_existing_download(self):
        self.destination.write_bytes(b'previous download')
        def cancel(current,total):
            if current: raise InterruptedError('cancelled')
        with self.assertRaises(InterruptedError): self.fetch(progress=cancel)
        self.assertEqual(self.destination.read_bytes(), b'previous download')
        self.assertEqual(list(self.destination.parent.iterdir()), [self.destination])

    def test_nonofficial_urls_and_symlink_destinations_are_rejected(self):
        for url in ('http://www.xetal.net/file', 'https://other.example/file', 'https://user:secret@www.xetal.net/file'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                download({**self.artifact,'url':url}, self.destination,
                         opener=lambda *_a,**_k:self.fail('Untrusted URL fetched'))
        other=self.destination.parent/'original';other.write_bytes(b'keep')
        self.destination.symlink_to(other)
        with self.assertRaises(ValueError):self.fetch()
        self.assertEqual(other.read_bytes(), b'keep')

    def test_redirect_is_rejected_before_contacting_another_host(self):
        for url in ('https://other.example/file','http://www.xetal.net/file','https://www.xetal.net:8443/file'):
            with self.assertRaises(ValueError):
                OfficialRedirect().redirect_request(None,None,302,'redirect',{},url)


if __name__ == '__main__': unittest.main()
