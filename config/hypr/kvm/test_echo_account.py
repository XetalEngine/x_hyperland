"""Session boundaries and password-wallet behavior; no real account or wallet."""
import json
import subprocess
import threading
import unittest
from unittest.mock import patch
import echo_account


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.wallet=patch('echo_account.subprocess.run',return_value=subprocess.CompletedProcess([],0,'','')).start()
        self.which=patch('echo_account.shutil.which',return_value='/fixture/secret-tool').start()
        self.request=patch('echo_account.request',return_value={
            'token':'fixture-session-token','user':{'username':'test-user'}}).start()
        self.addCleanup(patch.stopall)
        self.account=echo_account.Account()

    def test_password_prefill_does_not_authenticate_or_read_old_tokens(self):
        self.wallet.return_value.stdout=json.dumps({'login':'test-user','password':'fixture-password'})
        self.assertFalse(self.account.token)
        self.wallet.assert_not_called();self.request.assert_not_called()
        saved=self.account.saved_credentials()
        self.assertEqual(saved,{'login':'test-user','password':'fixture-password'})
        self.assertFalse(self.account.token);self.assertEqual(self.account.user,{})
        self.request.assert_not_called()
        self.assertIn('xetal-kvm-password',self.wallet.call_args.args[0])
        self.assertNotIn('xetal-kvm',self.wallet.call_args.args[0])

    def test_remember_saves_only_password_and_login_through_stdin(self):
        self.account.login('test-user','fixture-password','654321',remember=True)
        store=next(call for call in self.wallet.call_args_list if call.args[0][1]=='store')
        self.assertEqual(json.loads(store.kwargs['input']),{'login':'test-user','password':'fixture-password'})
        self.assertNotIn('fixture-password',' '.join(store.args[0]))
        self.assertNotIn('fixture-session-token',str(self.wallet.call_args_list))
        self.assertNotIn('654321',str(self.wallet.call_args_list))
        self.request.assert_called_once_with('login',{'login':'test-user','password':'fixture-password','totp':'654321'})

    def test_close_keeps_password_but_requires_another_server_login(self):
        self.account.login('test-user','fixture-password',remember=True)
        self.wallet.reset_mock()
        self.account.end_session()
        self.assertEqual((self.account.token,self.account.user),('',{}))
        self.wallet.assert_not_called()
        with self.assertRaises(echo_account.AccountError):self.account.check()
        self.account.login('test-user','fixture-password')
        self.assertEqual([call.args[0] for call in self.request.call_args_list],['login','login'])

    def test_logout_removes_password_and_legacy_token(self):
        self.account.login('test-user','fixture-password')
        self.wallet.reset_mock();self.account.forget()
        applications=[call.args[0][3] for call in self.wallet.call_args_list]
        self.assertEqual(applications,['xetal-kvm','xetal-kvm-password'])
        self.assertEqual((self.account.token,self.account.user),('',{}))

    def test_wallet_failure_does_not_keep_logout_authenticated(self):
        self.account.login('test-user','fixture-password')
        self.wallet.side_effect=OSError('wallet unavailable')
        with self.assertRaisesRegex(echo_account.AccountError,'Logged out'):self.account.forget()
        self.assertFalse(self.account.token);self.assertEqual(self.account.user,{})

    def test_no_wallet_never_writes_a_password_fallback(self):
        self.which.return_value=None
        self.account.login('test-user','fixture-password',remember=True)
        self.assertEqual(self.account.saved_credentials(),{})
        self.wallet.assert_not_called()

    def test_malformed_or_legacy_saved_value_is_not_a_session(self):
        for value in ('fixture-session-token','null','[]','{"token":"fixture-session-token"}',
                      '{"login":"test-user","password":false}','x'*16385):
            with self.subTest(value=value[:30]):
                self.wallet.return_value.stdout=value
                self.assertEqual(self.account.saved_credentials(),{})
                self.assertFalse(self.account.token)
        self.request.assert_not_called()

    def test_queued_login_from_closed_window_never_contacts_server(self):
        session=self.account.session;self.account.end_session()
        with self.assertRaises(echo_account.AccountError):
            self.account.login('test-user','fixture-password',session=session)
        self.request.assert_not_called();self.wallet.assert_not_called()

    def finish_request_after_close(self,work,blocked):
        started=threading.Event();release=threading.Event();errors=[]
        def pending(*args,**kwargs):
            started.set()
            if not release.wait(5):raise RuntimeError('test request timed out')
            return blocked.return_value
        blocked.side_effect=pending
        def run():
            try:work()
            except Exception as error:errors.append(error)
        thread=threading.Thread(target=run);thread.start()
        try:
            self.assertTrue(started.wait(5))
            self.account.end_session()
        finally:release.set();thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors),1);self.assertIsInstance(errors[0],echo_account.AccountError)
        self.assertEqual((self.account.token,self.account.user),('',{}))

    def test_inflight_login_cannot_sign_in_after_close(self):
        self.finish_request_after_close(lambda:self.account.login('test-user','fixture-password'),self.request)
        self.wallet.assert_not_called()

    def test_slow_wallet_cannot_restore_session_after_close(self):
        self.finish_request_after_close(lambda:self.account.login('test-user','fixture-password',remember=True),self.wallet)

    def test_inflight_account_check_cannot_repopulate_closed_session(self):
        self.account.login('test-user','fixture-password')
        self.finish_request_after_close(self.account.check,self.request)

    def test_expired_or_banned_session_returns_to_logged_out(self):
        for status in (401,403):
            with self.subTest(status=status):
                self.account.token='fixture-session-token';self.account.user={'username':'test-user'}
                self.request.side_effect=echo_account.AccountError('not authorized',status=status)
                with self.assertRaises(echo_account.AccountError):self.account.check()
                self.assertEqual((self.account.token,self.account.user),('',{}))

    def test_transient_connection_failure_does_not_claim_a_new_login(self):
        self.account.login('test-user','fixture-password')
        self.request.side_effect=echo_account.AccountError('connection unavailable')
        with self.assertRaises(echo_account.AccountError):self.account.check()
        self.assertEqual(self.account.token,'fixture-session-token')


if __name__=='__main__':unittest.main()
