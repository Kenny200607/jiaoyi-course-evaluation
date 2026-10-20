import contextlib
import io
import tempfile
import unittest
import copy
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch


class PublicCliTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_check_reports_manual_login_without_opening_browser(self):
        import app
        (self.root/'config.ini').write_text('[user-account]\nusername=\npassword=\n')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = app.main(['--check'], base_dir=self.root)
        self.assertEqual(code, 0)
        self.assertIn('manual', out.getvalue())
        self.assertFalse((self.root/'logs').exists())

    def test_real_submission_is_cancelled_before_browser_start(self):
        import app
        (self.root/'config.ini').write_text('[evaluation-option]\nsubmit=true\n')
        with patch('builtins.input', return_value='no'), patch('logincopy.run_evaluation_flow') as run:
            code = app.main([], base_dir=self.root)
        self.assertEqual(code, 0)
        run.assert_not_called()

    def test_config_error_is_nonzero_and_does_not_echo_credentials(self):
        import app
        (self.root/'config.ini').write_text('[user-account]\nusername=private-student\n')
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            code = app.main(['--check'], base_dir=self.root)
        self.assertNotEqual(code, 0)
        self.assertNotIn('private-student', out.getvalue())

    def test_privacy_filter_redacts_urls_and_split_credential_writes(self):
        from privacy import RedactingStream
        out = io.StringIO()
        stream = RedactingStream(out, secrets=['private-secret', 'private-student'])
        stream.write('Login private-')
        stream.write('secret https://portal.example/Reply?recordId=one&token=abc#session\n')
        stream.flush()
        text = out.getvalue()
        for secret in ('private-secret', 'recordId=one', 'token=abc', '#session'):
            self.assertNotIn(secret, text)
        self.assertIn('https://portal.example/Reply', text)

    def test_quoted_sensitive_keys_and_internal_state_keys_are_redacted(self):
        from privacy import redact
        for text in ('Accepted browser alert: {"token": "synthetic-private-token"}',
                     '{"stateKey": "course-evaluation-submit:synthetic-record-id"}',
                     "{'password': 'synthetic-private-password'}"):
            with self.subTest(text=text):
                self.assertNotIn('synthetic-', redact(text))

    def test_legacy_script_uses_public_ini_from_unrelated_directory(self):
        import logincopy
        path = self.root/'config.ini'
        path.write_text('[user-account]\nusername=\npassword=\n')
        result = subprocess.run([sys.executable, '-X', 'utf8', logincopy.__file__, '--check', '--config', str(path)],
                                cwd=self.root, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('manual', result.stdout)

    def test_blank_credentials_wait_for_manual_login_without_filling_fields(self):
        import logincopy
        config = copy.deepcopy(logincopy.DEFAULT_CONFIG)
        session = logincopy.LoginCopySession(config)
        class Browser:
            title = 'Login'
            current_url = 'https://example.test/'
            def get(self, url):
                self.current_url = url
        session.driver = Browser()
        session._selenium = {'By': object(), 'EC': object()}
        completed = []
        session._is_webvpn_logged_in = lambda: False
        session._wait_until_webvpn_logged_in = lambda **kwargs: completed.append(True)
        session.login_webvpn()
        self.assertEqual(completed, [True])


if __name__ == '__main__':
    unittest.main()
