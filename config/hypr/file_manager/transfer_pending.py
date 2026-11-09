"""Disk-backed decisions for one transfer; errors never hold up unrelated files."""
import errno
import json
import stat
import time


class Conflict(OSError):
    def __init__(self, previous, replace_allowed):
        super().__init__(errno.EEXIST, 'An item with this name already exists in the destination.')
        self.previous, self.replace_allowed = previous, replace_allowed


class SpecialFile(OSError):
    def __init__(self, mode):
        self.kind = ('socket' if stat.S_ISSOCK(mode) else 'named pipe' if stat.S_ISFIFO(mode)
                     else 'device' if stat.S_ISCHR(mode) or stat.S_ISBLK(mode) else 'special file')
        super().__init__(errno.EOPNOTSUPP,
            f'This {self.kind} has no ordinary file contents to copy. Choose Skip to keep it at its original '
            'location and continue. Retrying or administrator access cannot copy a runtime endpoint.')


def retry_allowed(category):
    return category.rsplit(':', 1)[-1] not in ('socket', 'named pipe', 'device', 'special file')


def resolution(db, source, target, stage, moving, finished=False):
    """Describe the completed step, without claiming an unfinished move succeeded."""
    steps = {'directory_done': 'Folder attributes saved', 'verify': 'Copy verified',
             'precheck': 'Original checked', 'sync': 'Saved to disk'}
    if stage in steps: return steps[stage]
    row = db.execute('SELECT kind,removed,retained FROM entries WHERE source=? AND target=? ORDER BY id DESC LIMIT 1',
                     (source, target)).fetchone()
    if not row:
        # A previously unreadable item may turn out to be a socket after access
        # is granted. Do not describe that retry as a successful file copy.
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ignored_sockets'").fetchone() and \
           db.execute('SELECT 1 FROM ignored_sockets WHERE source=? AND target=?', (source, target)).fetchone():
            return 'Runtime socket ignored'
        return 'Folder processed' if stage == 'rescan' else 'Step completed'
    kind, removed, retained = row
    if removed: return 'Moved successfully'
    if stage == 'remove': return 'Original kept'
    # A folder can be traversed successfully while a child still needs a choice.
    if kind == 'directory': return 'Folder processed'
    if moving: return 'Copied; original kept' if retained or finished else 'Copied; move pending'
    return 'Copied successfully'


class Pending:
    def __init__(self, transfer):
        self.t = transfer
        self.count = 0
        self.total = 0
        self.automatic = 0
        self.last_commit = time.monotonic()
        self.policies = {}
        self.t.db.execute('''CREATE TABLE issues (
            id INTEGER PRIMARY KEY, source TEXT, target TEXT, stage TEXT, category TEXT,
            detail TEXT, task TEXT, status TEXT, choice TEXT, replace_allowed INTEGER, version INTEGER DEFAULT 1,
            UNIQUE(source,target,stage))''')
        self.t.db.execute('CREATE INDEX pending_status ON issues(status,id)')

    def emit(self, identifier, finished=False):
        row = self.t.db.execute('SELECT source,target,stage,category,detail,status,replace_allowed,version FROM issues WHERE id=?', (identifier,)).fetchone()
        self.t.emit(dict(event='issue', id=identifier, source=row[0], destination=row[1],
                         stage=row[2], category=row[3], detail=row[4], status=row[5],
                         replace_allowed=bool(row[6]), version=row[7], retry_allowed=retry_allowed(row[3]),
                         resolution=resolution(self.t.db, row[0], row[1], row[2], self.t.moving, finished)
                                    if row[5] == 'resolved' else ''))

    def finish(self):
        # Revisit only queue rows, using indexed journal lookups. In particular,
        # a cross-device move is not complete merely because its retry copied data.
        for (identifier,) in self.t.db.execute("SELECT id FROM issues WHERE status='resolved'"):
            self.emit(identifier, finished=True)

    def add(self, task, error):
        stage = task['kind']
        category = stage + ':' + ('conflict' if isinstance(error, Conflict) else
            error.kind if isinstance(error, SpecialFile) else 'permission' if isinstance(error, PermissionError)
            or error.errno in (errno.EACCES, errno.EPERM) else str(error.errno or 'io'))
        can_replace = isinstance(error, Conflict) and error.replace_allowed
        detail = error.strerror or str(error)
        if isinstance(error, Conflict):
            task['replace_expected'] = error.previous
            category += ':file' if can_replace else ':folder'
        old = self.t.db.execute('SELECT id,status FROM issues WHERE source=? AND target=? AND stage=?',
                               (task['source'], task['target'], stage)).fetchone()
        if old and old[1] in ('pending', 'authorizing', 'retry', 'skipped'): return  # Already decided/queued.
        if old:
            identifier = old[0]
            if old[1] == 'working': detail = 'Retry failed: ' + detail
            self.t.db.execute('UPDATE issues SET category=?,detail=?,task=?,status=?,choice=NULL,replace_allowed=?,version=version+1 WHERE id=?',
                (category, detail, json.dumps(task), 'pending', can_replace, identifier))
        else:
            identifier = self.t.db.execute('INSERT INTO issues(source,target,stage,category,detail,task,status,replace_allowed) VALUES (?,?,?,?,?,?,?,?)',
                (task['source'], task['target'], stage, category, detail, json.dumps(task), 'pending', can_replace)).lastrowid
            self.total += 1
        self.count += 1
        policy = self.policies.get(category)
        if policy == 'skip':
            self.choose(identifier, 'skip', publish=False)
            self.automatic += 1
        else:
            self.emit(identifier)
        # Commit both completed work and queued errors, including when the user
        # leaves the queue open. No in-memory list of every transferred file.
        if policy != 'skip' or time.monotonic() - self.last_commit >= .25:
            self.t.db.commit(); self.last_commit = time.monotonic()

    def choose(self, identifier, choice, publish=True):
        row = self.t.db.execute('SELECT task,status,category,replace_allowed FROM issues WHERE id=?', (identifier,)).fetchone()
        if not row or row[1] != 'pending': return
        if choice not in ('skip', 'retry', 'replace', 'authorize'): return
        if choice == 'retry' and not retry_allowed(row[2]): return
        if choice == 'replace' and not row[3]: return
        if choice == 'authorize' and not row[2].endswith(':permission'): return
        task = json.loads(row[0])
        if choice == 'skip':
            self.t.skip_task(task)
            self.count -= 1
        self.t.db.execute('UPDATE issues SET status=?,choice=? WHERE id=?',
                          ('skipped' if choice == 'skip' else 'authorizing' if choice == 'authorize' else 'retry', choice, identifier))
        if publish: self.emit(identifier)

    def authorization_finished(self):
        # Only this thread touches the journal. Authentication runs separately
        # so a password prompt cannot hold up unrelated copies.
        state, message = self.t.access.authorization()
        if state not in ('authorized', 'failed'): return
        rows = self.t.db.execute("SELECT id FROM issues WHERE status='authorizing'").fetchall()
        for (identifier,) in rows:
            if state == 'authorized':
                self.t.db.execute("UPDATE issues SET status='retry' WHERE id=?", (identifier,))
            else:
                self.t.db.execute("UPDATE issues SET status='pending',choice=NULL,version=version+1,detail=? WHERE id=?",
                    ('Administrator access was not granted. ' + message, identifier))
            self.emit(identifier)
        if rows: self.t.db.commit()

    def accept(self):
        self.authorization_finished()
        with self.t.control.condition:
            decisions, self.t.control.decisions = self.t.control.decisions, []
        for decision in decisions:
            ids = decision.get('ids', [])
            if not isinstance(ids, list): continue
            versions = decision.get('versions', {})
            if not isinstance(versions, dict): continue
            choice = decision.get('choice')
            for identifier in ids:
                if type(identifier) is not int: continue
                row = self.t.db.execute('SELECT category,status,version FROM issues WHERE id=?', (identifier,)).fetchone()
                # A delayed/double-click reply to an earlier error must never
                # authorize overwriting a destination that changed meanwhile.
                if not row or row[1] != 'pending' or versions.get(str(identifier)) != row[2]: continue
                if decision.get('all') is True:
                    # Only skipping is a lasting error policy. Retrying applies
                    # once to currently queued peers, never an endless loop.
                    if choice == 'skip': self.policies[row[0]] = 'skip'
                    for (peer,) in self.t.db.execute("SELECT id FROM issues WHERE category=? AND status='pending'", (row[0],)).fetchall():
                        self.choose(peer, choice)
                else: self.choose(identifier, choice)
        if decisions:
            if self.t.db.execute("SELECT 1 FROM issues WHERE status='authorizing' LIMIT 1").fetchone():
                self.t.access.request_authorization()
                self.authorization_finished()
            self.t.db.commit()

    def drain(self):
        t = self.t
        previous_phase = t.phase
        while self.count:
            t.control.check(); self.accept()
            row = t.db.execute("SELECT id,task,choice FROM issues WHERE status='retry' ORDER BY id LIMIT 1").fetchone()
            if row:
                identifier, encoded, choice = row
                task = json.loads(encoded)
                t.db.execute("UPDATE issues SET status='working' WHERE id=?", (identifier,))
                self.count -= 1
                self.emit(identifier)
                t.phase = 'Retrying queued items'
                t.current, t.target = task['source'], task['target']
                try:
                    t.retry_task(task, choice)
                except OSError as error:
                    self.add(task, error)
                else:
                    # A retried directory can discover different failed children;
                    # the directory's own resolved row must not hide those rows.
                    state = t.db.execute('SELECT status FROM issues WHERE id=?', (identifier,)).fetchone()[0]
                    if state == 'working':
                        t.db.execute("UPDATE issues SET status='resolved' WHERE id=?", (identifier,))
                        self.emit(identifier)
                t.db.commit()
            elif self.count:
                t.phase = 'Waiting for queued items'; t.current = ''
                t.progress(True)
                with t.control.condition:
                    if not t.control.decisions and not t.control.cancelled: t.control.condition.wait(.25)
        t.phase = previous_phase
        t.progress(True)


def export_report(journal, stream):
    """Stream a read-only snapshot, including every automatic skip, to a file."""
    from datetime import datetime, timezone
    from pathlib import Path
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(Path(journal).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        moving = json.loads(db.execute('SELECT value FROM meta').fetchone()[0]).get('operation') == 'move'
        stream.write('Fusion Files transfer report\nSnapshot: ' + datetime.now(timezone.utc).isoformat() + '\n')
        for source, target, stage, detail, status in db.execute('SELECT source,target,stage,detail,status FROM issues ORDER BY id'):
            result = resolution(db, source, target, stage, moving, finished=True) if status == 'resolved' else ''
            stage = {'item':'Copying', 'root':'Copying', 'rescan':'Reading folder', 'directory_done':'Folder attributes',
                     'verify':'Verifying copies', 'precheck':'Checking originals', 'remove':'Removing originals', 'sync':'Saving to disk'}.get(stage, stage)
            if result: stream.write(f'\n{result}\nOriginal issue: {detail}')
            else: stream.write(f'\n{detail}')
            stream.write(f'\nFrom: {source}\nTo: {target}\nStage: {stage}\nStatus: {result or status}\n')
        # Older journals predate this table. Runtime endpoints have no queue
        # rows, but an optional saved report can still explain their omission.
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ignored_sockets'").fetchone():
            for source, target in db.execute('SELECT source,target FROM ignored_sockets ORDER BY source,target'):
                stream.write(f'\nRuntime socket ignored automatically; excluded from file totals.\n'
                             f'From: {source}\nTo: {target}\nStatus: ignored / original kept\n')


if __name__ == '__main__':
    import argparse
    import sys
    parser = argparse.ArgumentParser(description='Export a Fusion Files transfer report.')
    parser.add_argument('--report', required=True)
    export_report(parser.parse_args().report, sys.stdout)
