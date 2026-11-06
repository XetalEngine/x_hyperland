#!/usr/bin/env python3
"""Debian root authentication through PAM when no desktop pkexec is installed."""
import errno
import os
from pathlib import Path
import pty
import re
import secrets
import select
import shlex
import signal
import subprocess
import sys
import termios
import time

import runtime_install as runtime


class AuthenticationError(RuntimeError):
    pass


class AuthenticationCancelled(AuthenticationError):
    pass


def root_password():
    result = subprocess.run(['/usr/bin/python3', str(Path(__file__).with_name('askpass.py')), '--root'],
                            stdout=subprocess.PIPE, timeout=600)
    if result.returncode:
        raise AuthenticationCancelled('Root authentication was cancelled.')
    password = bytearray(result.stdout)
    result.stdout = None
    if password.endswith(b'\n'):
        del password[-1:]
    return password


def stop(pid):
    """su forwards termination to its command and closes the PAM session."""
    try:
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic()+4
        while time.monotonic() < deadline:
            if os.waitpid(pid, os.WNOHANG)[0]:
                return
            time.sleep(.05)
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
    except (ChildProcessError, ProcessLookupError):
        pass


def exchange(command, marker, prompt, output, timeout=30):
    """Own the terminal, suppress authentication output, and stream only the command."""
    pid, terminal = pty.fork()
    if pid == 0:
        try:
            os.execvpe(command[0], command, {**os.environ, 'LC_ALL': 'C'})
        except OSError:
            os._exit(127)
    authenticated = False
    submitted = False
    pending = bytearray()
    deadline = time.monotonic()+timeout
    reaped = False
    try:
        while True:
            if not authenticated and time.monotonic() > deadline:
                raise AuthenticationError('Root authentication timed out. Retry Setup.')
            if not select.select([terminal], [], [], .1)[0]:
                continue
            try:
                data = os.read(terminal, 65536)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
            if not data:
                break
            if authenticated:
                output(data.replace(b'\r\n', b'\n'))
                continue
            pending.extend(data)
            if marker in pending:
                _, remainder = pending.split(marker, 1)
                authenticated = True
                pending.clear()
                output(bytes(remainder).replace(b'\r\n', b'\n'))
            elif re.search(rb'(?i)password:\s*$', pending):
                if submitted:
                    raise AuthenticationError('Root authentication failed. Retry with the root password.')
                # Never write a password into an echoing terminal, or forward
                # PAM's terminal output to the installer log after submission.
                if termios.tcgetattr(terminal)[3] & termios.ECHO:
                    raise AuthenticationError('The root password terminal is not private. Setup stopped.')
                password = prompt()
                try:
                    if not isinstance(password, bytearray) or b'\n' in password or b'\r' in password or b'\0' in password:
                        raise AuthenticationError('The root password could not be submitted.')
                    if termios.tcgetattr(terminal)[3] & termios.ECHO:
                        raise AuthenticationError('The root password terminal is not private. Setup stopped.')
                    password.append(10)
                    offset = 0
                    while offset < len(password):
                        offset += os.write(terminal, memoryview(password)[offset:])
                finally:
                    if isinstance(password, bytearray):
                        password[:] = b'\0'*len(password)
                        password.clear()
                pending.clear()
                submitted = True
                deadline = time.monotonic()+timeout
            elif len(pending) > 8192:
                del pending[:-8192]
        _, status = os.waitpid(pid, 0)
        reaped = True
        if not authenticated:
            raise AuthenticationError('Root authentication failed. Use the system root password.')
        code = os.waitstatus_to_exitcode(status)
        return code if code >= 0 else 128-code
    finally:
        if not reaped:
            stop(pid)
        os.close(terminal)


def run(command, prompt=None, output=None):
    if not runtime.policy.debian_host() or not command:
        raise RuntimeError('This authentication helper requires Debian 13 and a Setup command.')
    from debian_administrator import desktop_account
    account = desktop_account(os.getuid())
    marker = ('XETAL_ROOT_READY_'+secrets.token_hex(16)).encode()
    payload = ['/usr/bin/python3', str(Path(__file__).resolve()), '--exec', str(account.pw_uid), marker.decode(), *command]
    args = ['/usr/bin/su', '--login', '--shell', '/bin/sh', '--command', shlex.join(payload), 'root']
    if output is None:
        def output(data):
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
    return exchange(args, marker, prompt or root_password, output)


def execute(uid, marker, command):
    """Executed by su only after the root account has authenticated through PAM."""
    if os.geteuid() != 0 or not runtime.policy.debian_host() or not command:
        raise RuntimeError('Debian administrator authentication is required.')
    from debian_administrator import desktop_account
    account = desktop_account(int(uid))
    if not re.fullmatch(r'XETAL_ROOT_READY_[0-9a-f]{32}', marker):
        raise RuntimeError('Invalid administrator authentication exchange.')
    environment = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root', 'USER': 'root',
                   'LOGNAME': 'root', 'LC_ALL': 'C', 'DEBIAN_FRONTEND': 'noninteractive',
                   'XETAL_SETUP_SU_UID': str(account.pw_uid)}
    print(marker, flush=True)
    os.execvpe(command[0], command, environment)


if __name__ == '__main__':
    try:
        if sys.argv[1:2] == ['--exec'] and len(sys.argv) >= 5:
            execute(sys.argv[2], sys.argv[3], sys.argv[4:])
        else:
            def cancelled(signum, frame):
                raise AuthenticationCancelled('Debian administrator operation was cancelled.')
            for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGQUIT):
                signal.signal(signum, cancelled)
            sys.exit(run(sys.argv[1:]))
    except AuthenticationCancelled as error:
        print(str(error), file=sys.stderr)
        sys.exit(runtime.DEBIAN_AUTH_CANCELLED)
    except (AuthenticationError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        sys.exit(runtime.DEBIAN_AUTH_FAILED)
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
