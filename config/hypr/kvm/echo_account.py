"""Echo account client. Credentials never enter command lines or VM profiles."""
import json
import subprocess
import shutil
import threading
import urllib.request
import urllib.error
from packages import SITE
from download_access import NoRedirect

MAX_REPLY = 32768


class AccountError(RuntimeError):
    def __init__(self, message, *, status=None):
        super().__init__(message)
        self.status=status


def request(action, fields, *, site=SITE):
    from urllib.parse import urlsplit
    url = urlsplit(site)
    if url.scheme != 'https' or url.username or url.password or url.query or url.fragment:
        raise AccountError('Echo sign-in requires a secure website connection.')
    req = urllib.request.Request(site+'/api/kvm-session.php',
        data=json.dumps(dict(fields, action=action)).encode(),
        headers={'Content-Type':'application/json', 'User-Agent':'XetalKVM/2'})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=25) as reply:
            raw = reply.read(MAX_REPLY+1)
        if len(raw)>MAX_REPLY: raise ValueError('response size')
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get('ok') is not True:
            raise ValueError('response')
        return result
    except urllib.error.HTTPError as error:
        status=error.code; error.close()
        messages={401:'Sign in to Echo again to continue.', 403:'This Echo account cannot use the selected edition.',
                  409:'Xetallic MAX is coming soon.', 429:'Too many attempts. Wait a moment and try again.'}
        raise AccountError(messages.get(status, 'Echo is unavailable. Please try again later.'),status=status) from None
    except (OSError, ValueError, urllib.error.URLError):
        raise AccountError('Could not reach Echo securely. Please try again.') from None


class Account:
    def __init__(self):
        self.token=''; self.user={}; self.wallet_warning=''
        self._lock=threading.Lock()
        self._session=object()

    @property
    def session(self):
        with self._lock:return self._session

    def end_session(self):
        """Closing Settings expires access immediately, including pending logins."""
        with self._lock:
            self._session=object()
            self.token=''; self.user={}; self.wallet_warning=''

    def _require_session(self, session):
        # Call while holding _lock; no network/wallet operation holds this lock.
        if session is not self._session:
            raise AccountError('KVM Settings was closed or logged out. Click Login to sign in again.')

    @property
    def can_remember(self):
        return bool(shutil.which('secret-tool'))

    def saved_credentials(self):
        """Prefill only. Never restore a token or contact Echo automatically."""
        if not self.can_remember:return {}
        try:
            result=subprocess.run(['secret-tool','lookup','application','xetal-kvm-password','site',SITE],
                                  capture_output=True,text=True,timeout=15)
            if result.returncode or len(result.stdout)>16384:return {}
            saved=json.loads(result.stdout)
            if (isinstance(saved,dict) and set(saved)=={'login','password'}
                    and all(isinstance(value,str) and value for value in saved.values())):
                return saved
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
        return {}

    def login(self, login, password, totp='', remember=False, *, session=None):
        session=self.session if session is None else session
        with self._lock:self._require_session(session)
        result=request('login', {'login':login, 'password':password, 'totp':totp})
        token=result.get('token', '')
        user=result.get('user',{})
        if (not isinstance(token,str) or not 1<=len(token)<=128
                or not isinstance(user,dict) or not isinstance(user.get('username'),str)
                or not user['username']):
            raise AccountError('Echo returned an invalid session.')
        with self._lock:
            self._require_session(session)
            self.token=token; self.user=user; self.wallet_warning=''
        warning=''
        if self.can_remember:
            try:
                # Older releases stored a reusable token under this name. It is
                # never read; remove it when the user next signs in explicitly.
                self._clear_wallet('xetal-kvm')
                if remember:
                    saved=subprocess.run(['secret-tool','store','--label=Xetal KVM · Echo password',
                        'application','xetal-kvm-password','site',SITE],
                        input=json.dumps({'login':login,'password':password}),text=True,capture_output=True,timeout=30)
                    if saved.returncode:raise OSError('Could not save password')
                else:
                    self._clear_wallet('xetal-kvm-password')
            except (OSError, subprocess.TimeoutExpired):
                warning='Your password-wallet choice could not be saved. Check the Xetal KVM entry in your password wallet.'
        with self._lock:
            self._require_session(session)
            self.wallet_warning=warning
            return self.user

    def check(self):
        with self._lock:token=self.token;session=self._session
        if not token:raise AccountError('Sign in to Echo to use Enhanced free.')
        try:result=request('account', {'token':token})
        except AccountError as error:
            if error.status in (401,403):
                with self._lock:
                    if session is self._session:
                        self._session=object();self.token='';self.user={}
            raise
        user=result.get('user',{})
        if not isinstance(user,dict) or not isinstance(user.get('username'),str) or not user['username']:
            raise AccountError('Echo returned an invalid account.')
        with self._lock:
            self._require_session(session)
            self.user=user
            return self.user

    def forget(self):
        self.end_session()
        if self.can_remember:
            try:
                self._clear_wallet('xetal-kvm')
                self._clear_wallet('xetal-kvm-password')
            except (OSError, subprocess.TimeoutExpired):
                raise AccountError('Logged out. Remove the saved Xetal KVM login from your password wallet.') from None

    def _clear_wallet(self, application):
        result=subprocess.run(['secret-tool','clear','application',application,'site',SITE],
                              capture_output=True,text=True,timeout=15)
        # libsecret returns 1 without an error when no matching item exists.
        if result.returncode and (result.returncode!=1 or result.stderr):
            raise OSError('The password wallet could not remove its saved login.')
