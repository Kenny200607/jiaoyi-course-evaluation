import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess

from logincopy import DEFAULT_CONFIG, LoginCopySession


class BrowserSupportTests(unittest.TestCase):
    def test_parses_edge_driver_vendor_version_banner(self):
        session = LoginCopySession(copy.deepcopy(DEFAULT_CONFIG))
        banner = 'Microsoft Edge WebDriver 155.0.4283.62 (test-build)'
        with patch('logincopy.subprocess.run', return_value=subprocess.CompletedProcess([], 0, banner)):
            self.assertEqual(session._driver_version(Path('msedgedriver.exe')), '155.0.4283.62')

    def test_reads_installed_browser_windows_file_version(self):
        from browser_support import find_browser, file_version
        import sys
        if sys.platform != 'win32':
            self.skipTest('Windows native version API')
        binary = find_browser({'driver': 'Chrome'}) or find_browser({'driver': 'Edge'})
        if binary is None:
            self.skipTest('No installed browser')
        self.assertRegex(file_version(binary) or '', r'^\d+\.\d+\.\d+\.\d+$')

    def test_edge_selects_real_edge_webdriver_options(self):
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['browser']['driver'] = 'Edge'
        loaded = LoginCopySession(config)._load_selenium()
        self.assertEqual(loaded['Options']().capabilities['browserName'], 'MicrosoftEdge')
        self.assertIn('.edge.', loaded['Service'].__module__)

    def test_edge_driver_version_uses_first_three_components(self):
        from browser_support import versions_match
        self.assertTrue(versions_match('Edge', '155.0.123.10', '155.0.123.1'))
        self.assertFalse(versions_match('Edge', '155.0.123.10', '155.0.124.1'))
        self.assertTrue(versions_match('Chrome', '155.0.123.10', '155.0.124.1'))
        self.assertFalse(versions_match('Chrome', '155.0.123.10', '154.0.123.10'))

    def test_explicit_missing_browser_is_not_silently_replaced(self):
        from browser_support import find_browser
        with self.assertRaises(ValueError):
            find_browser({'driver': 'Edge', 'chrome_binary': 'missing-explicit-browser.exe'})

    def test_edge_auto_detection_uses_edge_not_chrome(self):
        from browser_support import find_browser
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            edge = root/'Microsoft/Edge/Application/msedge.exe'
            edge.parent.mkdir(parents=True)
            edge.touch()
            self.assertEqual(find_browser({'driver': 'Edge'}, roots=[root]), str(edge))


if __name__ == '__main__':
    unittest.main()
