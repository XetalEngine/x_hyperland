"""Quiet close saves configuration and drafts without applying VM operations."""
import json
import shutil
from pathlib import Path
from settings_defaults import atomic_write
import launcher


def save(window):
    editor = getattr(window, 'tab_opencore', None)
    if editor:
        editor.flush()
        editor.save_draft()
    # Capture both texts before any refresh can replace the other editor.
    edits = [(e.key, e.edit.toPlainText()) for e in
             (window.tab_proc.start, window.tab_proc.revert) if e.edit.document().isModified()]
    for key, content in edits:
        launcher.save_hook(key, content)
    window.cfg.sync()
    window.cfg.compact()
    path = window._paths().session
    if path.is_file(): shutil.copyfile(path, str(path)+'.prev')
    window.cfg.save(path)
    window._baseline = json.dumps(window.cfg.data, sort_keys=True)


def recover(window, error):
    """Keep a recovery copy even if the normal session destination is unwritable."""
    import tempfile
    path = Path(tempfile.mkdtemp(prefix='xetal-kvm-recovery-'))
    atomic_write(path/'session.json', (json.dumps(window.cfg.data, indent=2)+'\n').encode())
    (path/'error.txt').write_text(str(error)+'\n')
    print('KVM settings recovery saved to '+str(path), flush=True)
