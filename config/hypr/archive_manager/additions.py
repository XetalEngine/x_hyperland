"""Stage archive additions and reuse normal transfer choices for member conflicts."""
import errno
import os
from pathlib import Path
import stat

from engine import ArchiveError, safe_member


def prepare(task, runner, archive, work):
    sources = list(dict.fromkeys(os.path.abspath(path) for path in task.request.get('add', [])))
    if not sources: raise ArchiveError('Choose files or folders to add.')
    for name in sources:
        path = Path(name)
        if not path.name: raise ArchiveError('Choose files or folders inside a filesystem.')
        if path.resolve() == Path(task.request['sources'][0]).resolve():
            raise ArchiveError('An archive cannot be added to itself.')
        if path.is_dir() and not path.is_symlink() and (
                Path(task.request['sources'][0]).resolve().is_relative_to(path.resolve()) or
                work.resolve().is_relative_to(path.resolve())):
            raise ArchiveError('Choose a source folder that does not contain this archive or its temporary work.')
    folder = task.request.get('folder', '')
    folder = safe_member(folder) if folder else ''
    if folder == '.': folder = ''
    task.set_phase('Checking archive folders')
    index = task.index(runner, archive, work/'add-members.sqlite')
    try:
        index.validate(); index.build_tree(task.control)
        if folder:
            entry = index.db.execute('SELECT directory FROM tree WHERE path=?', (folder,)).fetchone()
            if not entry or not entry[0]:
                raise ArchiveError('The destination folder is no longer in this archive. Reload it and try again.')

        # Snapshot the incoming selection before finding conflicts. New files
        # appearing in the original folders cannot bypass an overwrite choice.
        incoming = work/'incoming'; incoming.mkdir()
        task.transfer(sources, incoming, phase='Preparing files to add',
                      display_destination=(incoming, 'Incoming files'))
        roots = list(incoming.iterdir())
        if not roots: return incoming, []
        staged = work/'additions'; staged.mkdir()
        directories = []
        markers = []

        def directory(path):
            missing = []
            while path != staged and not path.exists():
                missing.append(path); path = path.parent
            for child in reversed(missing):
                child.mkdir(); directories.append((child, child.stat().st_ino))

        destination = staged/folder
        directory(destination)
        pending = [(path, '/'.join(filter(None, (folder, path.name)))) for path in roots]
        while pending:
            task.control.check()
            path, member = pending.pop()
            if safe_member(member) != member:
                raise ArchiveError('This file name cannot be represented safely inside the archive: '+member)
            info = path.lstat(); is_directory = stat.S_ISDIR(info.st_mode)
            existing = index.db.execute('SELECT directory FROM tree WHERE path=?', (member,)).fetchone()
            if existing and not (is_directory and existing[0]):
                marker = staged/member
                directory(marker.parent)
                if existing[0]: directory(marker)
                else:
                    marker.touch(exist_ok=False)
                    markers.append((marker, marker.stat().st_ino))
                # A folder cannot merge into an archived file. The transfer
                # queue offers Skip; don't manufacture children below it.
                if is_directory: continue
            if is_directory:
                with os.scandir(path) as children:
                    pending.extend((Path(child.path), member+'/'+child.name) for child in children)

        task.transfer(roots, destination, phase='Adding files to archive',
                      display_source=(incoming, 'Incoming files'),
                      display_destination=(staged, str(Path(task.request['sources'][0]).absolute())))
        # A skipped collision leaves its empty marker. Accepted copies replace
        # it atomically with a different inode. Never feed skipped markers to 7z.
        for marker, inode in markers:
            task.control.check()
            try:
                if marker.lstat().st_ino == inode: marker.unlink()
            except FileNotFoundError: pass
        for path, inode in reversed(directories):
            try:
                if path.lstat().st_ino == inode: path.rmdir()
            except OSError as error:
                if error.errno not in (errno.ENOENT, errno.ENOTEMPTY, errno.EEXIST): raise
        names = [str((destination/path.name).relative_to(staged)) for path in roots
                 if os.path.lexists(destination/path.name)]
        return staged, names
    finally:
        index.close()
