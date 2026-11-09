#!/usr/bin/env python3
"""Read-only, bounded search worker. JSON request on stdin; JSON events on stdout.

Names use shell wildcards plus Windows *.* / *. conventions. Content uses
ripgrep's linear-time regex engine; no shell, index, elevation or file writes.
Each GUI search owns a process group so cancellation also stops its readers.
"""
from __future__ import annotations

import base64
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import fnmatch
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time


def patterns(value):
    return [part.strip() for part in re.split(r'[;|\n]', value) if part.strip()]


def name_matches(name, expression, sensitive=False, partial=True):
    if not sensitive:
        name, expression = name.casefold(), expression.casefold()
    for pattern in patterns(expression) or ['*']:
        if pattern in ('*', '*.*'): return True
        if pattern == '*.':
            if Path(name).suffix in ('', '.'): return True
        elif not any(char in pattern for char in '*?[') and partial:
            if pattern in name: return True
        elif fnmatch.fnmatchcase(name, pattern): return True
    return False


def options(value):
    if not isinstance(value, dict): raise ValueError('Invalid search request.')
    root = value.get('root', '')
    if not isinstance(root, str) or not os.path.isabs(root) or not os.path.isdir(root):
        raise ValueError('Choose an existing local or mounted folder to search.')
    result = {'root': os.path.realpath(root)}
    for key, default in {'query':'', 'names':'*', 'types':'', 'exclude':'', 'encoding':'auto'}.items():
        text = value.get(key, default)
        if not isinstance(text, str) or len(text) > 8192 or '\0' in text:
            raise ValueError('The search expression is too long or contains an invalid character.')
        result[key] = text
    for key, default in {'contents':False, 'regex':False, 'case':False, 'word':False,
                         'recursive':True, 'hidden':False, 'follow':False, 'binary':False,
                         'multiline':False, 'folders':True}.items():
        if type(value.get(key, default)) is not bool: raise ValueError('Invalid search option: '+key)
        result[key] = value.get(key, default)
    for key, default, maximum in (('workers',0,32), ('limit',20000,100000),
                                 ('min_size',0,2**53), ('max_size',0,2**53),
                                 ('after',0,2**40), ('before',0,2**40)):
        number = value.get(key, default)
        if type(number) is not int or number < 0 or number > maximum:
            raise ValueError('Invalid search limit: '+key)
        result[key] = number
    if not result['limit']: raise ValueError('Choose a result limit of at least one.')
    if not result['query'].strip(): raise ValueError('Enter a name, wildcard or text to find.')
    if result['max_size'] and result['min_size'] > result['max_size']:
        raise ValueError('Minimum size must not exceed maximum size.')
    if result['after'] and result['before'] and result['after'] >= result['before']:
        raise ValueError('The modified-date range is reversed.')
    if result['encoding'] not in ('auto','utf-8','utf-16le','utf-16be','windows-1252'):
        raise ValueError('Choose a supported text encoding.')
    result['workers'] = result['workers'] or min(4, os.cpu_count() or 1)
    return result


class Search:
    def __init__(self, request, emit):
        self.options = options(request); self.emit = emit
        self.lock = threading.RLock(); self.cancelled = threading.Event()
        self.processes = set(); self.pending = []; self.last_flush = 0.
        self.stats = dict(scanned=0, searched=0, rows=0, matches=0, skipped=0, errors=0, binary=0, long_lines=0)
        self.started = time.monotonic(); self.limited = False
        self.rg = shutil.which('rg')

    def progress(self, force=False):
        with self.lock:
            if not force and time.monotonic()-self.last_flush < .15: return
            if self.pending:
                self.emit({'event':'rows', 'rows':self.pending}); self.pending = []
            self.emit({'event':'progress', **self.stats, 'seconds':round(time.monotonic()-self.started, 2)})
            self.last_flush = time.monotonic()

    def count(self, key, amount=1):
        with self.lock: self.stats[key] += amount

    def error(self, text):
        with self.lock:
            self.stats['errors'] += 1
            if self.stats['errors'] <= 8: self.emit({'event':'warning', 'message':text[:1500]})

    def stop(self):
        self.cancelled.set()
        with self.lock:
            for process in tuple(self.processes):
                if process.poll() is None:
                    try: process.terminate()
                    except ProcessLookupError: pass

    def row(self, entry):
        with self.lock:
            if self.cancelled.is_set(): return
            self.stats['rows'] += 1; self.stats['matches'] += entry.get('matches', 0)
            self.pending.append(entry)
            if len(self.pending) >= 64: self.progress(True)
            if self.stats['rows'] >= self.options['limit']:
                self.limited = True; self.stop()

    def excluded(self, path, name):
        relative = os.path.relpath(path, self.options['root']).replace(os.sep, '/')
        for pattern in patterns(self.options['exclude']):
            pattern = pattern.strip('/')
            candidate = relative if '/' in pattern else name
            if name_matches(candidate, pattern, self.options['case'], partial=False): return True
        return False

    def entries(self):
        # Iterators keep wide directories bounded; inode identities break symlink loops.
        stack = []; visited = set()
        def descend(path):
            try:
                info = os.stat(path); identity = (info.st_dev, info.st_ino)
                if identity in visited: return
                visited.add(identity); stack.append(os.scandir(path))
            except OSError as exc: self.error(str(exc))
        descend(self.options['root'])
        try:
            while stack and not self.cancelled.is_set():
                try: entry = next(stack[-1])
                except StopIteration: stack.pop().close(); continue
                except OSError as exc: self.error(str(exc)); stack.pop().close(); continue
                self.count('scanned'); self.progress()
                if not self.options['hidden'] and entry.name.startswith('.'): continue
                if self.excluded(entry.path, entry.name): continue
                try:
                    if entry.is_symlink() and not self.options['follow']: continue
                    info = entry.stat(follow_symlinks=self.options['follow'])
                    directory = stat.S_ISDIR(info.st_mode)
                    if directory:
                        if self.options['recursive']: descend(entry.path)
                        if self.options['contents'] or not self.options['folders']: continue
                    elif not stat.S_ISREG(info.st_mode): continue
                    yield (entry.path, info, directory)
                except OSError as exc: self.error(str(exc))
        finally:
            for iterator in stack: iterator.close()

    def eligible(self, entry):
        path, info, directory = entry; o = self.options; name = os.path.basename(path)
        if not name_matches(name, o['names'] if o['contents'] else o['query'], o['case']): return False
        if o['types'] and (directory or not name_matches(name, o['types'], o['case'], partial=False)): return False
        if o['after'] and info.st_mtime < o['after']: return False
        if o['before'] and info.st_mtime >= o['before']: return False
        if not directory and (info.st_size < o['min_size'] or (o['max_size'] and info.st_size > o['max_size'])):
            self.count('skipped'); return False
        return True

    def record(self, entry):
        path, info, directory = entry
        return dict(path=path, name=os.path.basename(path), size=info.st_size if not directory else 0,
                    modified=int(info.st_mtime), directory=directory, line=0, column=0,
                    matches=0, preview='')

    def arguments(self):
        o = self.options
        command = [self.rg, '--no-config', '--json', '--threads', '1', '--line-number',
                   '--with-filename', '--color', 'never', '--no-ignore', '--no-mmap', '--crlf',
                   '--encoding', o['encoding'], '--engine', 'default']
        if not o['regex']: command.append('--fixed-strings')
        if not o['case']: command.append('--ignore-case')
        if o['word']: command.append('--word-regexp')
        command.append('--text' if o['binary'] else '--no-binary')
        if o['multiline']: command.extend(['--multiline', '--multiline-dotall'])
        command.extend(['--regexp', o['query']])
        return command

    @staticmethod
    def decoded(field):
        if 'text' in field: return field['text']
        return base64.b64decode(field.get('bytes','')).decode('utf-8', errors='replace')

    def batch(self, entries):
        entries = [entry for entry in entries if self.eligible(entry)]
        if not entries or self.cancelled.is_set(): return
        if not self.options['contents']:
            for entry in entries:
                if self.cancelled.is_set(): break
                self.row(self.record(entry))
            return
        lookup = {entry[0]:entry for entry in entries}
        # A file used for stderr prevents a full error pipe from stalling stdout.
        # ripgrep can emit matches before discovering a NUL byte. Stage each
        # file's rows until its end event so binary files cannot leak partial,
        # misleading results. Large match sets spill to an anonymous temp file.
        with tempfile.TemporaryFile() as errors, tempfile.SpooledTemporaryFile(max_size=512*1024) as staged:
            staged_count = 0
            process = subprocess.Popen([*self.arguments(), '--', *lookup], stdout=subprocess.PIPE,
                                       stderr=errors, stdin=subprocess.DEVNULL)
            with self.lock:
                self.processes.add(process)
                if self.cancelled.is_set(): process.terminate()
            try:
                while not self.cancelled.is_set():
                    raw = process.stdout.readline(2*1024*1024)
                    if not raw: break
                    if not raw.endswith(b'\n'):
                        while raw and not raw.endswith(b'\n') and not self.cancelled.is_set():
                            raw = process.stdout.readline(2*1024*1024)
                        self.count('long_lines'); continue
                    event = json.loads(raw); data = event.get('data', {})
                    if event['type'] == 'begin':
                        self.count('searched'); staged.seek(0); staged.truncate(); staged_count = 0
                    elif event['type'] == 'end':
                        if data.get('binary_offset') is not None and not self.options['binary']:
                            self.count('binary')
                        else:
                            staged.seek(0)
                            for saved in staged:
                                if self.cancelled.is_set(): break
                                self.row(json.loads(saved))
                    elif event['type'] == 'match':
                        path = self.decoded(data['path'])
                        if path not in lookup: continue
                        text = self.decoded(data['lines']); matches = data['submatches']
                        start = matches[0]['start'] if matches else 0
                        prefix = text.encode('utf-8')[:start].decode('utf-8', errors='replace')
                        offset = len(prefix); column = len(prefix.rsplit('\n',1)[-1])+1
                        excerpt = text[max(0,offset-90):offset+310].strip('\r\n')
                        excerpt = ''.join(c if c.isprintable() or c=='\t' else ' ' for c in excerpt)
                        row = self.record(lookup[path]); row.update(line=data['line_number']+prefix.count('\n'),
                            column=column, matches=len(matches), preview=excerpt)
                        if self.options['binary']: self.row(row)
                        elif staged_count < self.options['limit']:
                            staged.write(json.dumps(row, ensure_ascii=True).encode('utf-8')+b'\n')
                            staged_count += 1
                    self.progress()
                if self.cancelled.is_set() and process.poll() is None: process.terminate()
                code = process.wait()
                if code == 2 and not self.cancelled.is_set():
                    errors.seek(0); self.error(errors.read(4096).decode('utf-8', errors='replace'))
            finally:
                if process.poll() is None:
                    process.kill(); process.wait()
                process.stdout.close()
                with self.lock: self.processes.discard(process)

    def run(self):
        if self.options['contents']:
            if not self.rg: raise ValueError('Content search needs ripgrep. Install the ripgrep package, then retry.')
            check = subprocess.run(self.arguments(), input=b'', capture_output=True, timeout=5)
            if check.returncode == 2:
                raise ValueError(check.stderr.decode('utf-8', errors='replace').strip())
        self.emit({'event':'started', 'workers':self.options['workers'], 'root':self.options['root']})
        pending = set(); batch = []
        with ThreadPoolExecutor(max_workers=self.options['workers'], thread_name_prefix='fusion-search') as pool:
            for entry in self.entries():
                if self.cancelled.is_set(): break
                batch.append(entry)
                if len(batch) < 32: continue
                pending.add(pool.submit(self.batch, batch)); batch = []
                while len(pending) >= self.options['workers']*2 and not self.cancelled.is_set():
                    ready, pending = wait(pending, timeout=.15, return_when=FIRST_COMPLETED)
                    for future in ready: future.result()
                    self.progress()
            if batch and not self.cancelled.is_set(): pending.add(pool.submit(self.batch, batch))
            while pending:
                ready, pending = wait(pending, timeout=.15, return_when=FIRST_COMPLETED)
                for future in ready: future.result()
                self.progress()
        self.progress(True)
        self.emit({'event':'done', **self.stats, 'limited':self.limited,
                   'seconds':round(time.monotonic()-self.started,2)})


def main():
    def emit(value):
        print(json.dumps(value, ensure_ascii=True, separators=(',',':')), flush=True)
    try:
        request = sys.stdin.buffer.readline(128*1024)
        if len(request) >= 128*1024: raise ValueError('Search request is too large.')
        Search(json.loads(request), emit).run()
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        emit({'event':'error','message':str(exc)[:4000]}); return 1


if __name__ == '__main__': raise SystemExit(main())
