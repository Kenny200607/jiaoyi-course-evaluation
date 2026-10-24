"""Opt-in test of the actual extracted Windows ZIP, without school traffic."""
import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.environ.get('PORTABLE_TEST_DIR'), 'Opt-in extracted Windows ZIP tests')
class PackagedApplicationTests(unittest.TestCase):
    def test_dependencies_and_both_browsers_without_python_on_path(self):
        application = Path(os.environ['PORTABLE_TEST_DIR']).resolve()/'RunCourseEvaluation.exe'
        env = dict(os.environ)
        for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV'):
            env.pop(key, None)
        env['PATH'] = str(Path(os.environ['SystemRoot'])/'System32')+';'+os.environ['SystemRoot']
        with tempfile.TemporaryDirectory(prefix='portable驗證 空格') as temporary:
            directory = Path(temporary)
            ini = directory/'config.ini'
            for browser in ('Chrome', 'Edge'):
                ini.write_text('[user-account]\nusername=\npassword=\n[browser-option]\ndriver='+browser+'\n[evaluation-option]\nrating_level=3\n', encoding='utf-8-sig')
                for option in ('--check', '--diagnose', '--check-browser'):
                    result = subprocess.run([str(application), '--config', str(ini), option],
                                            cwd=directory, env=env, capture_output=True,
                                            text=True, encoding='utf-8', errors='replace', timeout=120)
                    self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                    if option == '--check':
                        self.assertEqual(json.loads(result.stdout)['rating_level'], 3)
                    if option == '--check-browser':
                        self.assertIn('Local browser check: PASS', result.stdout)
                result = subprocess.run([str(application), '--config', str(ini), '--rating-level', '5', '--check'],
                                        cwd=directory, env=env, capture_output=True,
                                        text=True, encoding='utf-8', errors='replace', timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertEqual(json.loads(result.stdout)['rating_level'], 5)


if __name__ == '__main__':
    unittest.main()
