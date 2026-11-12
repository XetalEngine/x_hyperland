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
        self.archive_ids = {}
        self.archive_pass = 0
        self.archive_condition = threading.Condition(threading.RLock())
        self.report_lock = threading.Lock()
        self.skip_categories = set()
        self.skipped_inputs = set()
        self.notes = []
        self.engine_cwd = os.getcwd()

    def send(self, value):
        # Passwords are kept only in memory and are never included in the report.
        # Qt queues Python objects by reference: later decisions must not rewrite
        # an earlier event before the GUI thread has received it.
        value = dict(value)
        if value.get('event') in ('issue', 'result', 'phase'):
            with self.report_lock:
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
        elif value.get('command') == 'issue_answer' and self.decide_archive(value): pass
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
        detail = (os.strerror(error['code']) if error.get('stage') in ('scan','open','read') else
                  '7-Zip could not process this archive member (code '+str(error['code'])+').')
        path = error.get('path','')
        if path and error.get('stage') in ('scan','open','read'): path = os.path.abspath(os.path.join(self.engine_cwd,path))
        key = (path,error.get('stage',''),error['code'])
        with self.archive_condition:
            previous = self.archive_rows.get(key)
            # The end-of-pass result repeats the live error events. Preserve an
            # already accepted choice instead of asking for it again.
            if previous and previous['pass'] == self.archive_pass: return dict(previous)
            self.issue_serial += 1
            row = dict(event='issue', id=previous['id'] if previous else -self.issue_serial,
                       version=previous['version']+1 if previous else 1, source=path,
                       destination=self.request.get('output',''), stage=self.phase,
                       category='archive:'+str(error['code']), detail=detail, status='pending',
                       retry_allowed=True, replace_allowed=False, **{'pass':self.archive_pass})
            self.archive_rows[key] = row; self.archive_ids[row['id']] = row
            if row['category'] in self.skip_categories or path in self.skipped_inputs:
                self.choose_archive(row,'skip',similar=row['category'] in self.skip_categories,automatic=True)
            else: self.send(row)
            return dict(row)

    def choose_archive(self, row, choice, similar=False, automatic=False):
        """Caller holds archive_condition; acknowledging never waits for 7-Zip."""
        row['status'] = 'skipped' if choice == 'skip' else 'retry'
        if choice == 'skip':
            if row['source']: self.skipped_inputs.add(row['source'])
            row['decisionText'] = ('Skipped automatically by your matching-issue choice. Original kept.' if automatic else
                                   'Skip accepted. This input is excluded from the archive; the original is kept.')
            if similar: row['decisionText'] += ' Current and later matching issues will also be skipped in this job.'
        else:
            row['decisionText'] = 'Retry accepted. The archive will be rebuilt after the current pass finishes.'
        self.send(row)

    def decide_archive(self, answer):
        ids = answer.get('ids',[])
        if not isinstance(ids,list) or not any(type(i) is int and i < 0 for i in ids): return False
        versions = answer.get('versions',{})
        if not isinstance(versions,dict): return True
        with self.archive_condition:
            selected = [self.archive_ids[i] for i in dict.fromkeys(i for i in ids if type(i) is int)
                        if i in self.archive_ids]
            choice = answer.get('choice')
            valid = [r for r in selected if r['status']=='pending' and versions.get(str(r['id']))==r['version']]
            if self.control.cancelled or choice not in ('skip','retry'): valid=[]
            if answer.get('all') is True:
                categories = {r['category'] for r in valid}
                if choice == 'skip': self.skip_categories.update(categories)
                valid = [r for r in self.archive_ids.values() if r['status']=='pending' and r['category'] in categories]
            for row in valid: self.choose_archive(row,choice,similar=answer.get('all') is True)
            # A stale/double-click decision cannot apply to a new issue revision.
            # Return its current state so a waiting UI can offer a fresh choice.
            for row in selected:
                if row not in valid: self.send(dict(row,decisionRejected=True))
            self.archive_condition.notify_all()
        return True

    def begin_archive_pass(self):
        with self.archive_condition:
            self.archive_pass += 1
            for row in self.archive_ids.values():
                if row['status']=='retry':
                    row['status']='working';row['decisionText']='Rebuilding the archive to retry this input.';self.send(row)

    def finish_archive_pass(self):
        with self.archive_condition:
            failed = {row['source'] for row in self.archive_ids.values() if row['pass']==self.archive_pass and row['status']!='resolved'}
            for row in self.archive_ids.values():
                if row['status']=='working' and row['pass'] < self.archive_pass:
                    row.update(status='resolved',resolution='Retry attempted' if row['source'] in failed else 'Archived successfully',
                               decisionText='This input has another issue; review its other row.' if row['source'] in failed else 'Included after retry. Original kept.')
                    self.send(row)

    def archive_exclusions(self, cwd):
        # Runner uses -spd: exclusions are literal paths, including * and ?.
        with self.archive_condition:
            return ['-x!'+os.path.relpath(path,cwd) for path in sorted(self.skipped_inputs)]

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
        ids = list(dict.fromkeys(self.archive_issue(error)['id'] for error in result.errors))
        if not ids:
            raise ArchiveError(result.output.strip() or f'7-Zip stopped with exit code {result.code}.')
        self.set_phase('Waiting for queued items')
        while True:
            self.control.check()
            with self.archive_condition:
                rows = [dict(self.archive_ids[i]) for i in ids]
                if all(row['status']!='pending' for row in rows): break
                self.archive_condition.wait(.1)
        return any(row['status']=='retry' for row in rows)

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
        while True:
            self.begin_archive_pass()
            self.set_phase('Compressing')
            for path in temporary.iterdir(): path.unlink()
            args = format_arguments(options)
            if kind.startswith('tar.'):
                tar = work/(output.name[:-len(kind)]+ 'tar' if output.name.lower().endswith(kind) else output.name+'.tar')
                tar.unlink(missing_ok=True)
                result = self.invoke(runner, ['a', '-ttar', '-snl', *self.archive_exclusions(cwd), '--', str(tar), *names], cwd=cwd)
                if result.code:
                    if result.code != 1: raise ArchiveError(result.output.strip())
                    retry = self.resolve_archive_errors(result)
                    self.finish_archive_pass()
                    if retry: continue
                result = self.invoke(runner, ['a', *args, '--', str(target), tar.name], cwd=work)
            else:
                result = self.invoke(runner, ['a', *args, *self.archive_exclusions(cwd), '--', str(target), *names], cwd=cwd)
            if result.code == 1:
                retry = self.resolve_archive_errors(result)
                self.finish_archive_pass()
                if retry: continue
            elif result.code: raise ArchiveError(result.output.strip() or 'Compression failed.')
            self.finish_archive_pass()
            break
        if self.skipped_inputs:
            self.notes.append(f'{len(self.skipped_inputs)} input item(s) were omitted with your approval.')
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
            if self.request.get('source_identity'):
                value=archive.stat()
                if [value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns]!=self.request['source_identity']:
                    raise ArchiveError('The archive changed after the drop. Reload it and drag the selection again.')
            self.set_phase('Reading archive')
            index = self.index(runner, archive, work/f'members-{n}.sqlite')
            try: index.validate()
            finally: index.close()
            extracted = work/f'extracted-{n}'; extracted.mkdir()
            selected = self.request.get('members', [])
            for member in selected: safe_member(member)
            if self.request.get('strip_common_parent') and not selected:
                raise ArchiveError('No archive entries were selected for this drop.')
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
            published=extracted
            if self.request.get('strip_common_parent'):
                # A dragged nested file lands in the chosen folder. Sibling
                # selections retain their layout below the common parent.
                prefix=os.path.commonpath([str(Path(safe_member(member)).parent) for member in selected])
                published=extracted/prefix
                if not published.is_dir():
                    raise ArchiveError('The selected entries could not be extracted. Reload the archive and try again.')
            if self.request.get('source_identity'):
                value=archive.stat()
                if [value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns]!=self.request['source_identity']:
                    raise ArchiveError('The archive changed during extraction. Existing destination files were kept.')
            self.publish(list(published.iterdir()), target, work)

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
                    try: index.build_tree(self.control)
                    finally: index.close()
                else: raise ArchiveError('Unknown archive operation.')
            result = {'ok':True, 'notes':self.notes, 'report':str(self.report)}
        except Cancelled: result = {'ok':False, 'cancelled':True, 'report':str(self.report)}
        except Exception as error: result = {'ok':False, 'error':str(error), 'report':str(self.report)}
        self.password = None
        self.request.pop('password', None)
        self.send(dict(result, event='result')); self.outcome.emit(result)
