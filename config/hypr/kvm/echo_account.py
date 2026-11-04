"""Echo account client. Credentials never enter command lines or VM profiles."""
import json
import subprocess
import shutil
import urllib.request
import urllib.error
from packages import SITE
from download_access import NoRedirect

MAX_REPLY = 32768


class AccountError(RuntimeError):
    pass


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
        raise AccountError(messages.get(status, 'Echo is unavailable. Please try again later.')) from None
    except (OSError, ValueError, urllib.error.URLError):
        raise AccountError('Could not reach Echo securely. Please try again.') from None


class Account:
    def __init__(self):
        self.token=''; self.user={}

    @property
    def can_remember(self):
        return bool(shutil.which('secret-tool'))

    def restore(self):
        if not self.can_remember: return False
        try:
            result=subprocess.run(['secret-tool','lookup','application','xetal-kvm','site',SITE],
                                  capture_output=True,text=True,timeout=15)
            self.token=result.stdout.strip() if result.returncode==0 else ''
            if not 1<=len(self.token)<=128: self.token=''
        except (OSError, subprocess.TimeoutExpired): self.token=''
        return bool(self.token)

    def login(self, login, password, totp='', remember=False):
        result=request('login', {'login':login, 'password':password, 'totp':totp})
        token=result.get('token', '')
        if not isinstance(token,str) or not 1<=len(token)<=128:
            raise AccountError('Echo returned an invalid session.')
        self.token=token; self.user=result.get('user', {})
        if self.can_remember:
            try:
                if remember:
                    saved=subprocess.run(['secret-tool','store','--label=Xetal KVM · Echo','application','xetal-kvm','site',SITE],
                        input=token, text=True,capture_output=True,timeout=30)
                    if saved.returncode:raise AccountError('Signed in for this session. The password wallet could not save the login.')
                else:
                    # An earlier remembered account must not reappear next time
                    # after this sign-in explicitly chose session-only access.
                    self._clear_wallet()
            except (OSError, subprocess.TimeoutExpired):
                raise AccountError('Signed in for this session. The password wallet did not respond.') from None
        return self.user

    def check(self):
        if not self.token: raise AccountError('Sign in to Echo to use Enhanced free.')
        result=request('account', {'token':self.token})
        self.user=result.get('user', {})
        return self.user

    def forget(self):
        self.token='';self.user={}
        if self.can_remember:
            try:self._clear_wallet()
            except (OSError, subprocess.TimeoutExpired):
                raise AccountError('Disconnected for this session. Remove the saved Xetal KVM login from your password wallet.') from None

    def _clear_wallet(self):
        result=subprocess.run(['secret-tool','clear','application','xetal-kvm','site',SITE],
                              capture_output=True,text=True,timeout=15)
        # libsecret returns 1 without an error when no matching item exists.
        if result.returncode and (result.returncode!=1 or result.stderr):
            raise OSError('The password wallet could not remove its saved login.')
