import copy
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from logincopy import DEFAULT_CONFIG, LoginCopySession


class DriverResolutionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.session = LoginCopySession(copy.deepcopy(DEFAULT_CONFIG))
        self.enterContext(patch('logincopy.Path.home', return_value=self.root))
        self.enterContext(patch('logincopy.shutil.which', return_value=None))
        self.enterContext(patch.object(self.session, '_chrome_major_version', return_value='155'))
        self.enterContext(patch.object(self.session, '_resolve_chrome_binary', return_value='chrome.exe'))

        def version(command, **_kwargs):
            return subprocess.CompletedProcess(command, 0, f'ChromeDriver {Path(command[0]).parent.name}')

        self.enterContext(patch('logincopy.subprocess.run', side_effect=version))

    def driver(self, version):
        path = self.root / '.cache/selenium/chromedriver/win64' / version / 'chromedriver.exe'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return path

    def test_selects_numeric_latest_matching_driver(self):
        self.driver('155.0.9.1')
        expected = self.driver('155.0.10.1')
        self.driver('156.0.1.1')
        self.assertEqual(self.session._resolve_chromedriver_path(), expected)

    def test_stale_configured_driver_does_not_override_matching_cache(self):
        self.session.config['browser']['chromedriver_path'] = str(self.driver('154.0.1.1'))
        expected = self.driver('155.0.1.1')
        self.assertEqual(self.session._resolve_chromedriver_path(), expected)

    def test_missing_matching_driver_uses_manager_instead_of_stale_cache(self):
        self.driver('154.0.1.1')
        expected = self.root / '155.0.2.1' / 'chromedriver.exe'
        expected.parent.mkdir()
        expected.touch()
        with patch.object(self.session, '_managed_chromedriver_path', return_value=expected, create=True):
            self.assertEqual(self.session._resolve_chromedriver_path(), expected)

    def test_manager_returning_wrong_version_is_rejected(self):
        wrong = self.driver('154.0.1.1')
        with patch.object(self.session, '_managed_chromedriver_path', return_value=wrong, create=True):
            with self.assertRaisesRegex(RuntimeError, '155'):
                self.session._resolve_chromedriver_path()


if __name__ == '__main__':
    unittest.main()
