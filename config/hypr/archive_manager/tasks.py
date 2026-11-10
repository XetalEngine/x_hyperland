"""Archive transactions run off the GUI thread; publishing reuses Fusion transfers."""
from pathlib import Path
import json
import os
import queue
import selectors
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid

from PyQt6.QtCore import QThread, pyqtSignal
from engine import (ArchiveError, Cancelled, Control, FORMATS, Index, PasswordRequired,
                    Runner, format_arguments, list_archive, safe_member)

ROOT = Path(__file__).resolve().parents[1]


def wrapped_tar(path):
    return str(path).lower().endswith(('.tar.gz','.tgz','.tar.xz','.txz','.tar.bz2','.tbz2','.tbz'))


def state_directory():
    root = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'fusion-files/archives'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


class Task(QThread):
    message = pyqtSignal(dict)
    outcome = pyqtSignal(dict)

    def __init__(self, request, parent=None):
        super().__init__(parent)
        self.request = dict(request)
        self.control = Control()
        self.answers = queue.Queue()
        self.transfer_process = None
        self.transfer_lock = threading.Lock()
        self.password = request.get('password')
        self.phase = ''
        self.report = state_directory()/(uuid.uuid4().hex+'.jsonl')
        self.issue_serial = 0
        self.archive_rows = {}
        self.notes = []
        self.engine_cwd = os.getcwd()

    def send(self, value):
        # Passwords are kept only in memory and are never included in the report.
        if value.get('event') in ('issue', 'result', 'phase'):
            with self.report.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(value, ensure_ascii=True)+'\n')
        self.message.emit(value)

    def command(self, value):
        if value.get('command') in ('pause', 'resume', 'cancel'):
            action = {'pause':'suspend', 'resume':'resume', 'cancel':'cancel'}[value['command']]
            with self.transfer_lock:
                transfer = self.transfer_process
                if transfer:
                    if action == 'cancel': self.control.cancelled = True
                    self.write_transfer(value)
                else: self.control.request(action)
            self.message.emit({'event':'paused', 'value': action == 'suspend'})
        elif value.get('command') == 'password': self.answers.put(value)
        else:
            with self.transfer_lock:
                if self.transfer_process: self.write_transfer(value)
                else: self.answers.put(value)

    def write_transfer(self, value):
        try:
            self.transfer_process.stdin.write((json.dumps(value)+'\n').encode())
            self.transfer_process.stdin.flush()
        except (BrokenPipeError, OSError): pass

    def set_phase(self, text):
        self.phase = text; self.send({'event':'phase', 'text':text})

    def progress(self, value):
        if value.get('event') == 'error':
            # Only input warnings during creation can be retried/skipped after
            # the current pass. Extraction/CRC failures abort the transaction;
            # the final result reports them, without a misleading action queue.
            if self.request['operation'] == 'compress' and value.get('stage') in ('scan','open','read'):
                self.archive_issue(value)
            return
        if value.get('event') == 'progress':
            value = dict(value, phase='Scanning files' if value.get('command','').strip().lower() == 'scan' else self.phase)
        self.message.emit(value)

    def archive_issue(self, error):
        key = (error.get('path',''), error.get('stage',''), error['code'])
        previous = self.archive_rows.get(key)
        if previous and previous['status'] == 'pending': return previous
        self.issue_serial += 1
        detail = (os.strerror(error['code']) if error.get('stage') in ('scan','open','read') else
                  '7-Zip could not process this archive member (code '+str(error['code'])+').')
        path = error.get('path','')
        if path and error.get('stage') in ('scan','open','read'): path = os.path.abspath(os.path.join(self.engine_cwd,path))
        row = dict(event='issue', id=previous['id'] if previous else -self.issue_serial,
                   version=previous['version']+1 if previous else 1, source=path,
                   destination=self.request.get('output',''), stage=self.phase,
                   category='archive:'+str(error['code']), detail=detail, status='pending',
                   retry_allowed=True, replace_allowed=False)
        self.archive_rows[key] = row; self.send(row); return row

    def get_password(self, wrong=False):
        self.message.emit({'event':'password', 'wrong':wrong})
        while True:
            self.control.check()
            try: answer = self.answers.get(timeout=.1)
            except queue.Empty: continue
            if answer.get('command') == 'password':
                if answer.get('password') is None: raise Cancelled()
                self.password = answer['password']; return

    def invoke(self, runner, arguments, cwd=None, entry=None):
        self.engine_cwd = str(cwd or os.getcwd())
        while True:
            try: result = runner.run(arguments, cwd=cwd, password=self.password, entry=entry)
            except PasswordRequired:
                self.get_password(); continue
            if result.code and ('Wrong password' in result.output or any(
                    error.get('stage') == 'extract' and error.get('code') == 9 for error in result.errors)):
                self.get_password(wrong=True); continue
            return result

    def index(self, runner, archive, database):
        while True:
            Path(database).unlink(missing_ok=True)
            index = Index(database)
            try:
                result = self.invoke(runner, ['l', '-slt', '--', str(archive)], entry=index.add)
                if result.code: raise ArchiveError(result.output.strip() or 'The archive could not be read.')
                index.db.commit(); return index
            except BaseException:
                index.close(); raise

    def resolve_archive_errors(self, result):
        """Continue compression's first pass, then require explicit omission/retry decisions."""
        rows = list({row['id']:row for row in (self.archive_issue(error) for error in result.errors)}.values())
        if not rows:
            raise ArchiveError(result.output.strip() or f'7-Zip stopped with exit code {result.code}.')
        self.set_phase('Waiting for queued items')
        decisions = {}
        while len(decisions) < len(rows):
            self.control.check()
            try: answer = self.answers.get(timeout=.1)
            except queue.Empty: continue
            if answer.get('command') != 'issue_answer': continue
            selected = [r for r in rows if r['id'] in answer.get('ids', []) and
                        answer.get('versions', {}).get(str(r['id'])) == r['version'] and r['id'] not in decisions]
            if answer.get('all'):
                categories = {r['category'] for r in selected}
                selected = [r for r in rows if r['category'] in categories and r['id'] not in decisions]
            for row in selected:
                choice = answer.get('choice')
                if choice not in ('skip', 'retry'): continue
                decisions[row['id']] = choice
                row['status'] = 'retry' if choice == 'retry' else 'skipped'
                self.send(row)
        retry = any(value == 'retry' for value in decisions.values())
        if not retry:
            self.notes.append(f'{len(rows)} input item(s) were omitted with your approval.')
        return retry, rows

    def transfer(self, sources, destination, moving=False):
        self.set_phase('Saving archive' if self.request['operation'] in ('compress','add','delete','rename') else 'Saving extracted files')
        journal = state_directory()/(uuid.uuid4().hex+'.sqlite')
        request = dict(operation='move' if moving else 'copy', sources=[str(p) for p in sources],
                       destination=str(destination), journal=str(journal))
        self.message.emit({'event':'transfer', 'journal':str(journal)})
        authority = None
        result = None
        process = subprocess.Popen(['/usr/bin/python3', '-I', str(ROOT/'file_manager/transfer_worker.py')],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        with self.transfer_lock:
            self.transfer_process = process; self.write_transfer(request)
        try:
            for line in process.stdout:
                value = json.loads(line)
                if value['event'] == 'authenticate':
                    pkexec = shutil.which('pkexec')
                    if not pkexec or (authority and authority.poll() is None):
                        with self.transfer_lock:
                            self.write_transfer(dict(command='auth_failed', token=value['token'], error='Administrator authentication is unavailable or still open.'))
                        continue
                    authority = subprocess.Popen([pkexec, '/usr/bin/python3', '-I', str(ROOT/'file_manager/transfer_authority.py')],
                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    authority.stdin.write(json.dumps(value).encode()); authority.stdin.close()
                    def authority_result(child=authority, token=value['token']):
                        if child.wait():
                            with self.transfer_lock:
                                if self.transfer_process:
                                    self.write_transfer(dict(command='auth_failed', token=token, error='Administrator authorization was canceled or failed.'))
                    threading.Thread(target=authority_result, daemon=True).start()
                elif value['event'] == 'result': result = value
                elif value['event'] == 'progress': self.message.emit(dict(value, event='transfer_progress'))
                elif value['event'] == 'issue': self.send(value)
            code = process.wait()
            if not result or not result.get('ok') or code:
                if result and result.get('cancelled'): raise Cancelled()
                raise ArchiveError((result or {}).get('error') or process.stderr.read().decode(errors='replace'))
            self.notes.extend(result.get('warnings', []))
            if result.get('skippedFiles'): self.notes.append('Some destination items were skipped.')
            self.control.check()
        finally:
            with self.transfer_lock:
                self.transfer_process = None
                if process.poll() is None:
                    process.stdin.write(b'{"command":"cancel"}\n'); process.stdin.flush()
            if process.poll() is None:
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            if authority and authority.poll() is None:
                try: authority.wait(timeout=3)
                except subprocess.TimeoutExpired: pass  # Scoped helper exits on worker EOF.
            for stream in (process.stdin,process.stdout,process.stderr):
                if stream: stream.close()

    def publish(self, sources, destination, work):
        """Let the transfer worker create new/protected destination folders too."""
        destination = Path(os.path.abspath(destination))
        ancestor = destination
        missing = []
        while ancestor != ancestor.parent:
            try:
                ancestor.lstat()
                break
            except FileNotFoundError:
                missing.append(ancestor.name)
                ancestor = ancestor.parent
            except PermissionError:
                break  # The worker can request scoped administrator access.
        if missing:
            wrapper = work/('publish-'+uuid.uuid4().hex)
            wrapper.mkdir()
            nested = wrapper.joinpath(*reversed(missing))
            nested.mkdir(parents=True)
            for source in sources:
                self.control.check()
                source.rename(nested/source.name)
            self.transfer([wrapper/missing[-1]], ancestor, moving=True)
        else:
            self.transfer(sources, destination, moving=True)

    def compress(self, runner, work):
        sources = [Path(os.path.abspath(p)) for p in self.request['sources']]
        if not sources: raise ArchiveError('Choose at least one file or folder.')
        output = Path(self.request['output'])
        if not output.name or '\x00' in str(output): raise ArchiveError('Choose an archive file name.')
        for source in sources:
            if source.is_dir() and os.path.commonpath((source.resolve(), output.resolve())) == str(source.resolve()):
                raise ArchiveError('Save the archive outside the folders being compressed.')
        cwd = Path(os.path.commonpath([str(p.parent) for p in sources]))
        names = [str(p.relative_to(cwd)) for p in sources]
        options = dict(self.request.get('options', {}))
        if self.password is not None: options['password'] = self.password
        format_arguments(options)  # Validate all options before writing.
        kind = options.get('format','7z')
        if kind in ('gz','xz','bz2') and (len(sources) != 1 or not sources[0].is_file()):
            raise ArchiveError('This format compresses one file. Choose tar.'+kind+' for folders or multiple files.')
        temporary = work/'output'; temporary.mkdir()
        target = temporary/output.name
        retry_rows = []
        while True:
            self.set_phase('Compressing')
            for path in temporary.iterdir(): path.unlink()
            args = format_arguments(options)
            if kind.startswith('tar.'):
                tar = work/(output.name[:-len(kind)]+ 'tar' if output.name.lower().endswith(kind) else output.name+'.tar')
                tar.unlink(missing_ok=True)
                result = self.invoke(runner, ['a', '-ttar', '-snl', '--', str(tar), *names], cwd=cwd)
                if result.code:
                    if result.code != 1: raise ArchiveError(result.output.strip())
                    retry, retry_rows = self.resolve_archive_errors(result)
                    if retry: continue
                result = self.invoke(runner, ['a', *args, '--', str(target), tar.name], cwd=work)
            else:
                result = self.invoke(runner, ['a', *args, '--', str(target), *names], cwd=cwd)
            if result.code == 1:
                retry, retry_rows = self.resolve_archive_errors(result)
                if retry: continue
            elif result.code: raise ArchiveError(result.output.strip() or 'Compression failed.')
            for row in retry_rows:
                if row['status'] == 'retry': self.send(dict(row, status='resolved', resolution='Archived successfully'))
            break
        self.set_phase('Verifying archive')
        parts = sorted(temporary.iterdir())
        if not parts: raise ArchiveError('7-Zip did not produce an archive.')
        result = self.invoke(runner, ['t', '--', str(parts[0])])
        if result.code: raise ArchiveError('The new archive failed verification.\n'+result.output.strip())
        if options.get('volume') and any(output.parent.glob(output.name+'.[0-9]*')):
            raise ArchiveError('A split archive with this name already exists. Choose a new archive name to keep complete volume sets together.')
        self.publish(parts, output.parent, work)

    def extract(self, runner, work):
        archives = self.request['sources']
        destination = Path(self.request['destination'])
        for n, path in enumerate(archives):
            archive = Path(path)
            self.set_phase('Reading archive')
            index = self.index(runner, archive, work/f'members-{n}.sqlite')
            try: index.validate()
            finally: index.close()
            extracted = work/f'extracted-{n}'; extracted.mkdir()
            selected = self.request.get('members', [])
            for member in selected: safe_member(member)
            self.set_phase('Extracting')
            args = ['x', '-y', '-aos', '-o'+str(extracted), '--', str(archive), *(selected if not wrapped_tar(archive) else [])]
            result = self.invoke(runner, args)
            if result.code: raise ArchiveError('Extraction failed; existing destination files were kept.\n'+result.output.strip())
            # A compressed tar is one archive in the UI, not a surprise .tar file.
            if wrapped_tar(archive):
                inner = list(extracted.iterdir())
                if len(inner) == 1 and inner[0].is_file():
                    nested = self.index(runner, inner[0], work/f'inner-{n}.sqlite')
                    try: nested.validate()
                    finally: nested.close()
                    unpacked = work/f'unpacked-{n}'; unpacked.mkdir()
                    result = self.invoke(runner, ['x','-y','-aos','-o'+str(unpacked),'--',str(inner[0]),*selected])
                    if result.code: raise ArchiveError(result.output.strip())
                    extracted = unpacked
            target = destination
            if self.request.get('separate'):
                name = archive.name
                for suffix in ('.tar.gz','.tar.bz2','.tar.xz','.7z.001','.zip.001','.tgz','.tbz2','.txz'):
                    if name.lower().endswith(suffix): name = name[:-len(suffix)]; break
                else: name = archive.stem
                target = destination/(name or 'Extracted files')
            self.publish(list(extracted.iterdir()), target, work)

    def modify(self, runner, work):
        archive = Path(self.request['sources'][0])
        if not archive.is_file() or archive.is_symlink(): raise ArchiveError('Choose a regular, writable archive.')
        if archive.name.endswith('.001'): raise ArchiveError('Extract split archives before modifying them.')
        self.set_phase('Preparing archive update')
        original = archive.stat()
        target = work/archive.name
        # Reflink when available, otherwise stream a copy with cancellation checks.
        with archive.open('rb') as src, target.open('wb') as dst:
            while chunk := src.read(1024*1024): self.control.check(); dst.write(chunk)
        operation = self.request['operation']
        if operation == 'add':
            inputs = [Path(os.path.abspath(p)) for p in self.request['add']]
            cwd = Path(os.path.commonpath([str(p.parent) for p in inputs]))
            arguments = ['a', '-snl', '--', str(target), *[str(p.relative_to(cwd)) for p in inputs]]
        elif operation == 'delete':
            cwd = work; arguments = ['d', '--', str(target), *self.request['members']]
        else:
            safe_member(self.request['new_name'])
            cwd = work; arguments = ['rn', '--', str(target), self.request['members'][0], self.request['new_name']]
        self.set_phase('Updating archive')
        result = self.invoke(runner, arguments, cwd=cwd)
        if result.code: raise ArchiveError('The original archive was kept.\n'+result.output.strip())
        self.set_phase('Verifying archive')
        result = self.invoke(runner, ['t','--',str(target)])
        if result.code: raise ArchiveError('The updated archive failed verification. The original was kept.\n'+result.output.strip())
        current = archive.stat()
        if (original.st_dev,original.st_ino,original.st_size,original.st_mtime_ns) != (current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns):
            raise ArchiveError('The original archive changed while it was being updated. Reload it and try again.')
        self.transfer([target], archive.parent, moving=True)

    def run(self):
        try:
            runner = Runner(self.control, self.progress)
            # Selected destination's filesystem supplies staging space; no size cap.
            destination = Path(self.request.get('output') or self.request.get('destination') or self.request['sources'][0])
            parent = destination.parent if not self.request.get('destination') else destination
            while not parent.is_dir() and parent != parent.parent: parent = parent.parent
            if not os.access(parent, os.W_OK | os.X_OK): parent = state_directory()
            with tempfile.TemporaryDirectory(prefix='.fusion-archive-', dir=parent) as temporary:
                work = Path(temporary)
                operation = self.request['operation']
                if operation == 'compress': self.compress(runner, work)
                elif operation == 'extract': self.extract(runner, work)
                elif operation in ('add','delete','rename'): self.modify(runner, work)
                elif operation == 'test':
                    self.set_phase('Testing archive')
                    for path in self.request['sources']:
                        result = self.invoke(runner, ['t','--',str(path)])
                        if result.code: raise ArchiveError(result.output.strip() or 'Archive integrity check failed.')
                elif operation == 'list':
                    self.set_phase('Reading archive')
                    archive=Path(self.request['sources'][0])
                    if wrapped_tar(archive):
                        outer=self.index(runner,archive,work/'outer.sqlite')
                        try:outer.validate()
                        finally:outer.close()
                        unpacked=work/'outer';unpacked.mkdir()
                        result=self.invoke(runner,['x','-y','-o'+str(unpacked),'--',str(archive)])
                        if result.code:raise ArchiveError(result.output.strip())
                        files=list(unpacked.iterdir())
                        if len(files)!=1 or not files[0].is_file():raise ArchiveError('The compressed tar does not contain one archive.')
                        archive=files[0]
                    index = self.index(runner, archive, self.request['index'])
                    index.close()
                else: raise ArchiveError('Unknown archive operation.')
            result = {'ok':True, 'notes':self.notes, 'report':str(self.report)}
        except Cancelled: result = {'ok':False, 'cancelled':True, 'report':str(self.report)}
        except Exception as error: result = {'ok':False, 'error':str(error), 'report':str(self.report)}
        self.password = None
        self.request.pop('password', None)
        self.send(dict(result, event='result')); self.outcome.emit(result)
