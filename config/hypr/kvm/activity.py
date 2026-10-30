"""Distinguish a live VM supervisor from its retained status/log files."""
from pathlib import Path


def supervisor_active(state,proc=Path('/proc')):
    if state.get('state') not in ('starting','running','stopping'):return False
    try:
        pid=int(state['pid'])
        if pid<=1:return False
        fields=(proc/str(pid)/'stat').read_text().rsplit(') ',1)[1].split()
        return fields[0] not in ('Z','X') and fields[19]==str(state['process_start'])
    except PermissionError:
        # An unreadable live supervisor must not authorize an update.
        return True
    except (OSError,KeyError,ValueError,IndexError,TypeError):return False
