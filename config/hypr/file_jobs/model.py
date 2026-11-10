"""State reported by file-operation clients; the UI never performs the operation."""
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit, urlunsplit
from PyQt6.QtCore import QObject, pyqtSignal

TEXT = {'title', 'infoMessage', 'descriptionLabel1', 'descriptionValue1',
        'descriptionLabel2', 'descriptionValue2', 'destUrl', 'errorMessage', 'currentFile', 'phase', 'warningMessage', 'operation'}
NUMBERS = {'totalBytes', 'processedBytes', 'totalFiles', 'processedFiles',
           'totalDirectories', 'processedDirectories', 'totalItems', 'processedItems',
           'percent', 'speed', 'elapsedTime', 'errorCode', 'skippedFiles', 'verifiedBytes', 'renamedItems', 'pendingIssues', 'issueCount', 'skippedFolders',
           'processedFolderAttributes', 'totalFolderAttributes'}
FLAGS = {'suspended', 'transient', 'immediate', 'totalsKnown'}


def location(value):
    """Display a path without exposing passwords embedded in remote URLs."""
    value = str(value or '')
    try:
        url = urlsplit(value)
        if url.scheme == 'file':
            return unquote(url.path)
        if url.scheme and url.netloc:
            host = url.hostname or ''
            if ':' in host: host = '[' + host + ']'
            if url.port: host += ':' + str(url.port)
            return urlunsplit((url.scheme, host, url.path, '', ''))
    except ValueError:
        return 'Remote location'
    return value


def short_location(value):
    value = location(value).rstrip('/')
    return unquote(PurePosixPath(urlsplit(value).path).name) or value or 'Files'


def amount(value):
    value = max(0, float(value))
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'):
        if value < 1024 or unit == 'PiB':
            return f'{value:.0f} {unit}' if unit == 'B' or value >= 100 else f'{value:.1f} {unit}'
        value /= 1024


class Job(QObject):
    changed = pyqtSignal()
    finished = pyqtSignal()
    requested = pyqtSignal(str)
    question_changed = pyqtSignal()
    answered = pyqtSignal(dict)
    queue_changed = pyqtSignal(object)
    queue_decision = pyqtSignal(dict)

    def __init__(self, path, owner, application, capabilities, hints=None, parent=None):
        super().__init__(parent)
        self.path, self.owner, self.application = path, owner, application
        self.capabilities = int(capabilities) & 3
        self.data = {}
        self.result = None
        self.pending = ''
        self.question = None
        self.queue_rows = {}
        self.queue_state = {}
        self.update(hints or {})

    def update_queue(self, values):
        """Presentation only: decisions return to the owning transfer worker."""
        if not isinstance(values, dict): return False
        changed = []
        for row in values.get('rows', []):
            if not isinstance(row, dict) or type(row.get('id')) is not int: continue
            row = dict(row)
            self.queue_rows[row['id']] = row
            changed.append(row)
        state = values.get('state', {})
        if isinstance(state, dict): self.queue_state.update(state)
        if changed or state: self.queue_changed.emit(changed)
        return True

    def decide_queue(self, ids, choice, similar=False, versions=None):
        if self.result is not None or self.pending == 'cancel' or self.queue_state.get('done'): return False
        if choice not in ('retry', 'skip', 'replace', 'authorize'): return False
        rows = [self.queue_rows[i] for i in dict.fromkeys(ids)
                if i in self.queue_rows and self.queue_rows[i].get('status') == 'pending']
        if not rows: return False
        # A replacement confirmation can stay open while the worker updates
        # the queue. Never approve a different revision than the user saw.
        if versions is not None and any(versions.get(str(r['id'])) != r.get('version') for r in rows): return False
        if choice == 'replace' and not all(r.get('replace_allowed') is True for r in rows): return False
        if choice == 'retry' and not all(r.get('retry_allowed', True) for r in rows): return False
        if choice == 'authorize' and not all(str(r.get('category', '')).endswith(':permission') for r in rows): return False
        self.queue_decision.emit({'ids': [r['id'] for r in rows],
            'versions': {str(r['id']): r.get('version') for r in rows}, 'choice': choice, 'all': bool(similar)})
        return True

    def update(self, values):
        if self.result is not None or not isinstance(values, dict):
            return
        changed = False
        for key, value in values.items():
            if key in TEXT and isinstance(value, str): value = value[:16384]
            elif key in NUMBERS and type(value) is int: value = max(0, min(2**64 - 1, value))
            elif key in FLAGS and type(value) is bool: pass
            else: continue
            if key == 'percent': value = min(100, value)
            if self.data.get(key) != value:
                self.data[key] = value
                changed = True
        if type(values.get('suspended')) is bool and self.pending in ('suspend', 'resume'):
            # An explicit state is the client's acknowledgement, including a
            # rejected pause during a non-suspendable stage of its operation.
            self.pending = ''; changed = True
        if changed: self.changed.emit()

    @property
    def percent(self):
        if self.result == 'done': return 100
        if self.data.get('totalsKnown') is False: return None
        if 'percent' in self.data: return self.data['percent']
        for unit in ('Bytes', 'Files', 'Items'):
            total = self.data.get('total' + unit, 0)
            if total > 0 and 'processed' + unit in self.data:
                return min(100, self.data['processed' + unit] * 100 / total)
        return None

    @property
    def running(self):
        return self.result is None and not self.question and not self.data.get('suspended') and self.pending != 'cancel' and self.data.get('phase') != 'Waiting for queued items'

    @property
    def title(self):
        title = self.data.get('title') or 'File operation'
        operation = {'Copying files': 'Copy', 'Moving files': 'Move', 'Linking files': 'Link', 'Undoing transfer': 'Undo'}.get(title)
        if operation and self.result:
            return operation + (' complete' if self.result == 'done' else ' canceled' if self.result == 'canceled' else ' stopped')
        return title

    @property
    def paths(self):
        first = self.data.get('descriptionValue1', '')
        second = self.data.get('descriptionValue2', '') or self.data.get('destUrl', '')
        return location(first), location(second)

    def summary(self):
        if self.result == 'done':
            skipped = self.data.get('skippedFiles', 0)
            if skipped: return f'Completed · {skipped:,} ' + ('item skipped' if skipped == 1 else 'items skipped')
            return 'Completed with notes' if self.data.get('warningMessage') else 'Completed'
        if self.result == 'canceled': return 'Canceled'
        if self.result == 'failed': return self.data.get('errorMessage') or 'The operation could not be completed.'
        if self.pending == 'cancel': return 'Canceling…'
        if self.question: return 'Waiting for your choice'
        if self.pending == 'suspend': return 'Pausing…'
        if self.pending == 'resume': return 'Resuming…'
        if self.data.get('suspended'): return 'Paused'
        if self.data.get('phase') == 'Waiting for queued items':
            pending = self.data.get('pendingIssues', 0)
            return f'{pending:,} queued ' + ('item needs a choice' if pending == 1 else 'items need a choice')
        pieces = []
        total, processed = self.data.get('totalBytes', 0), self.data.get('processedBytes', 0)
        if total: pieces.append(f'{amount(processed)} / {amount(total)}')
        elif processed: pieces.append(amount(processed))
        if self.data.get('totalFiles') or 'totalsKnown' in self.data: pieces.append(self.file_summary())
        speed = self.data.get('speed', 0)
        if speed: pieces.append(amount(speed) + '/s')
        return ' · '.join(pieces) or self.data.get('infoMessage') or 'Working…'

    def file_summary(self):
        if self.data.get('operation') in ('compress','extract','test','add','delete','rename','list'):
            count=self.data.get('processedFiles',0)
            text=f'{count:,} items processed' if count else ''
            pending=self.data.get('pendingIssues',0)
            if pending and self.result is None:text+=f' · {pending:,} queued'
            return text.strip(' ·')
        files = self.data.get('processedFiles', 0)
        if self.data.get('renamedItems') and not self.data.get('totalFiles'):
            renamed = self.data['renamedItems']
            text = f'{renamed:,} ' + ('item moved' if renamed == 1 else 'items moved')
        elif self.result is not None:
            text = f'{files:,} ' + ('file copied' if files == 1 else 'files copied')
        elif self.data.get('totalsKnown') is False:
            text = f'{files:,} files copied · Counting total…'
        else:
            text = f'{files:,} / {self.data.get("totalFiles", 0):,} files copied'
        skipped = self.data.get('skippedFiles', 0)
        if skipped: text += f' · {skipped:,} ' + ('item skipped' if skipped == 1 else 'items skipped')
        pending = self.data.get('pendingIssues', 0)
        if pending and self.result is None: text += f' · {pending:,} queued'
        return text

    def activity(self):
        if self.data.get('operation') in ('compress','extract','test','add','delete','rename','list') and self.result:
            return 'Archive operation finished' if self.result=='done' else 'Archive operation canceled' if self.result=='canceled' else 'Archive operation stopped'
        if self.result == 'done':
            return 'Skipped originals remain in place' if self.data.get('skippedFiles') else 'Transfer finished'
        if self.result is not None: return 'Completed copies are kept'
        phase = self.data.get('phase', 'Copying')
        if phase == 'Saving folder attributes':
            return f'{phase} · {self.data.get("processedFolderAttributes", 0):,} / {self.data.get("totalFolderAttributes", 0):,} folders'
        if phase == 'Waiting for queued items': return 'Waiting for your choice'
        return phase + (': ' + short_location(self.data['currentFile']) if self.data.get('currentFile') else '…')

    def request(self, action):
        if self.result is not None or self.pending == 'cancel': return False
        if action == 'review' and (self.data.get('issueCount', 0) or self.data.get('pendingIssues', 0)):
            self.requested.emit(action); return True
        if action == 'cancel' and not self.capabilities & 1: return False
        if action in ('suspend', 'resume'):
            if not self.capabilities & 2 or self.pending or self.question: return False
            if bool(self.data.get('suspended')) != (action == 'resume'): return False
        elif action != 'cancel': return False
        self.pending = action
        if action == 'cancel' and self.question: self.answer('cancel')
        self.changed.emit()
        self.requested.emit(action)
        return True

    def ask(self, values):
        if self.result is not None or self.pending == 'cancel' or self.question is not None:
            raise ValueError('This operation cannot accept another question.')
        if not isinstance(values, dict) or values.get('kind') not in ('conflicts', 'file', 'duplicate'):
            raise ValueError('Unsupported transfer question.')
        self.question = dict(kind=values['kind'],
            source=location(str(values.get('source', ''))[:16384]),
            destination=location(str(values.get('destination', ''))[:16384]),
            replace_allowed=values.get('replace_allowed') is True)
        self.question_changed.emit(); self.changed.emit()

    def answer(self, choice, apply_all=False):
        if not self.question: return False
        kind = self.question['kind']
        allowed = {'cancel'}
        if kind == 'duplicate': allowed.add('copy')
        else:
            allowed.add('skip')
            if self.question['replace_allowed']: allowed.add('replace')
            if kind == 'conflicts': allowed.add('individual')
        if choice not in allowed: return False
        self.question = None
        self.question_changed.emit(); self.changed.emit()
        self.answered.emit({'choice': choice, 'all': bool(apply_all and kind == 'file' and choice in ('replace', 'skip'))})
        return True

    def terminate(self, code=0, message=''):
        if self.result is not None: return
        if self.question: self.answer('cancel')
        self.result = 'done' if code == 0 else 'canceled' if code == 1 else 'failed'
        self.pending = ''
        self.data['errorMessage'] = str(message)[:16384]
        self.changed.emit()
        self.finished.emit()

    def disconnected(self):
        self.terminate(2, 'The application closed before reporting completion.')
