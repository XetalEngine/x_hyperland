"""State reported by file-operation clients; the UI never performs the operation."""
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit, urlunsplit
from PyQt6.QtCore import QObject, pyqtSignal

TEXT = {'title', 'infoMessage', 'descriptionLabel1', 'descriptionValue1',
        'descriptionLabel2', 'descriptionValue2', 'destUrl', 'errorMessage'}
NUMBERS = {'totalBytes', 'processedBytes', 'totalFiles', 'processedFiles',
           'totalDirectories', 'processedDirectories', 'totalItems', 'processedItems',
           'percent', 'speed', 'elapsedTime', 'errorCode'}
FLAGS = {'suspended', 'transient', 'immediate'}


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

    def __init__(self, path, owner, application, capabilities, hints=None, parent=None):
        super().__init__(parent)
        self.path, self.owner, self.application = path, owner, application
        self.capabilities = int(capabilities) & 3
        self.data = {}
        self.result = None
        self.pending = ''
        self.question = None
        self.update(hints or {})

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
        if 'percent' in self.data: return self.data['percent']
        for unit in ('Bytes', 'Files', 'Items'):
            total = self.data.get('total' + unit, 0)
            if total > 0 and 'processed' + unit in self.data:
                return min(100, self.data['processed' + unit] * 100 / total)
        return None

    @property
    def running(self):
        return self.result is None and not self.question and not self.data.get('suspended') and self.pending != 'cancel'

    @property
    def title(self):
        return self.data.get('title') or 'File operation'

    @property
    def paths(self):
        first = self.data.get('descriptionValue1', '')
        second = self.data.get('descriptionValue2', '') or self.data.get('destUrl', '')
        return location(first), location(second)

    def summary(self):
        if self.result == 'done': return 'Completed'
        if self.result == 'canceled': return 'Canceled'
        if self.result == 'failed': return self.data.get('errorMessage') or 'The operation could not be completed.'
        if self.pending == 'cancel': return 'Canceling…'
        if self.question: return 'Waiting for your choice'
        if self.pending == 'suspend': return 'Pausing…'
        if self.pending == 'resume': return 'Resuming…'
        if self.data.get('suspended'): return 'Paused'
        pieces = []
        total, processed = self.data.get('totalBytes', 0), self.data.get('processedBytes', 0)
        if total: pieces.append(f'{amount(processed)} / {amount(total)}')
        elif self.data.get('totalFiles'):
            pieces.append(f'{self.data.get("processedFiles", 0):,} / {self.data["totalFiles"]:,} files')
        speed = self.data.get('speed', 0)
        if speed: pieces.append(amount(speed) + '/s')
        return ' · '.join(pieces) or self.data.get('infoMessage') or 'Working…'

    def request(self, action):
        if self.result is not None or self.pending == 'cancel': return False
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
