"""Public rating settings and CLI behavior; no school connection."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from logincopy import DEFAULT_CONFIG
from release_config import load_public_config


class RatingConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()

    def load_ini(self, text=''):
        path = self.root/'config.ini'
        path.write_text('[evaluation-option]\n'+text, encoding='utf-8')
        return load_public_config(DEFAULT_CONFIG, path, self.root)

    def test_omitted_level_defaults_to_highest(self):
        self.assertEqual(self.load_ini()['evaluation'].get('ratingLevel'), 'highest')

    def test_ini_normalizes_highest_and_positive_levels(self):
        for value, expected in [('highest', 'highest'), (' Highest ', 'highest'), ('1', 1), ('3', 3), ('5', 5), ('7', 7)]:
            with self.subTest(value=value):
                self.assertEqual(self.load_ini('rating_level='+value)['evaluation']['ratingLevel'], expected)

    def test_invalid_ini_level_is_rejected(self):
        for value in ('0', '-1', '3.5', 'five', 'true', ''):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'rating_level'):
                self.load_ini('rating_level='+value)

    def test_json_level_is_validated_and_preserved(self):
        path = self.root/'custom.json'
        for value in (1, 3, 5):
            path.write_text(json.dumps({'evaluation': {'ratingLevel': value}}), encoding='utf-8')
            self.assertEqual(load_public_config(DEFAULT_CONFIG, path, self.root)['evaluation']['ratingLevel'], value)
        for value in (True, False, 0, -1, 3.5, None, [], {}):
            path.write_text(json.dumps({'evaluation': {'ratingLevel': value}}), encoding='utf-8')
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'rating_level'):
                load_public_config(DEFAULT_CONFIG, path, self.root)

    def test_cli_level_overrides_ini_without_starting_browser(self):
        self.load_ini('rating_level=2')
        application = Path(__file__).resolve().parents[1]/'app.py'
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(application),
                                 '--config', str(self.root/'config.ini'), '--check', '--rating-level', '4'],
                                capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['rating_level'], 4)
        self.assertFalse(output['evaluation_submit'])


if __name__ == '__main__':
    unittest.main()
