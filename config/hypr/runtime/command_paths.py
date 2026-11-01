"""Process-local command search paths for Setup and desktop tools."""
import os
from pathlib import Path

SYSTEM_TOOL_DIRS = ('/usr/local/sbin', '/usr/sbin', '/sbin')
PERL_SCRIPT_DIRS = ('/usr/bin/site_perl', '/usr/bin/vendor_perl', '/usr/bin/core_perl')


def extended_path(value):
    # Debian desktop logins can omit sbin, despite installing utilities there.
    # Arch's Perl directories can appear after login during package installation.
    # Recheck directories each time, preserving the caller's command precedence.
    paths = value.split(os.pathsep)
    for directory in (*SYSTEM_TOOL_DIRS, *PERL_SCRIPT_DIRS):
        if directory not in paths and Path(directory).is_dir():
            paths.append(directory)
    return os.pathsep.join(paths)
