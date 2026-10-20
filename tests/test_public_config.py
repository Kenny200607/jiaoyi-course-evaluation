import copy
import tempfile
import unittest
from pathlib import Path

from logincopy import DEFAULT_CONFIG


class PublicConfigTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def load(self, text, filename='config.ini'):
        from release_config import load_public_config
        path = self.root / filename
        path.write_text(text, encoding='utf-8-sig')
        return load_public_config(DEFAULT_CONFIG, path, self.root)

    def test_ini_preserves_password_punctuation_and_unicode(self):
        config = self.load('[user-account]\nusername=student-test\npassword=百分比%#;密碼\\end\n')
        self.assertEqual(config['credentials']['webvpn_password'], '百分比%#;密碼\\end')

    def test_blank_ini_never_reads_adjacent_developer_env(self):
        (self.root / '.env').write_text('USER_ID=private-student\nUSER_PASSWORD=private-secret\n')
        config = self.load('[user-account]\nusername=\npassword=\n')
        self.assertEqual(config['credentials'], {'webvpn_username': '', 'webvpn_password': ''})

    def test_explicit_json_does_not_inherit_adjacent_env(self):
        (self.root / '.env').write_text('USER_ID=private-student\nUSER_PASSWORD=private-secret\n')
        config = self.load('{"credentials": {"webvpn_username":"", "webvpn_password":""}}', 'custom.json')
        self.assertEqual(config['credentials']['webvpn_username'], '')

    def test_legacy_default_still_loads_existing_local_env(self):
        from release_config import load_public_config
        (self.root / '.env').write_text('USER_ID=legacy-student\nUSER_PASSWORD=legacy-secret\n')
        config = load_public_config(DEFAULT_CONFIG, base_dir=self.root)
        self.assertEqual(config['credentials']['webvpn_username'], 'legacy-student')

    def test_partial_credentials_are_rejected_without_echoing_value(self):
        with self.assertRaises(ValueError) as caught:
            self.load('[user-account]\nusername=private-student\n')
        self.assertNotIn('private-student', str(caught.exception))

    def test_invalid_options_are_errors(self):
        cases = [
            '[browser-option]\ndriver=Firefox\n',
            '[evaluation-option]\nsubmit=maybe\n',
            '[evaluation-option]\nmax_courses=-1\n',
            '[evaluation-option]\ndry_run_limit=0\n',
            '[browser-option]\nexe_path=missing-browser.exe\n',
            '[browser-option]\ndriver_path=missing-driver.exe\n',
        ]
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.load(text)

    def test_relative_paths_are_resolved_from_program_directory(self):
        binary = self.root / '瀏覽器 空格' / 'msedge.exe'
        binary.parent.mkdir()
        binary.touch()
        config = self.load('[browser-option]\ndriver=Edge\nexe_path=瀏覽器 空格/msedge.exe\n')
        self.assertEqual(config['browser']['driver'], 'Edge')
        self.assertEqual(Path(config['browser']['chrome_binary']), binary)
        self.assertEqual(Path(config['download']['download_dir']), self.root / 'downloads')

    def test_missing_explicit_file_does_not_create_or_fallback(self):
        from release_config import load_public_config
        with self.assertRaises(FileNotFoundError):
            load_public_config(DEFAULT_CONFIG, self.root/'typo.ini', self.root)
        self.assertFalse((self.root/'config.ini').exists())

    def test_first_run_creates_only_blank_template(self):
        from release_config import FirstRunConfig, load_public_config
        with self.assertRaises(FirstRunConfig):
            load_public_config(DEFAULT_CONFIG, base_dir=self.root)
        self.assertTrue((self.root/'config.ini').exists())
        config = load_public_config(DEFAULT_CONFIG, base_dir=self.root)
        self.assertEqual(config['credentials']['webvpn_password'], '')
        self.assertFalse(config['evaluation']['submit'])
        self.assertFalse(DEFAULT_CONFIG['evaluation']['submit'])


if __name__ == '__main__':
    unittest.main()
