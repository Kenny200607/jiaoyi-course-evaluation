import configparser
import tempfile
import unittest
import json
import hashlib
import zipfile
from pathlib import Path


class ReleaseArtifactTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_audit_rejects_populated_config_and_session_file(self):
        from tools.audit_release import audit_tree
        (self.root/'config.ini').write_text('[user-account]\nusername=student\npassword=secret\n')
        (self.root/'cookies.json').write_text('[]')
        errors = audit_tree(self.root)
        self.assertTrue(any('config.ini' in error for error in errors))
        self.assertTrue(any('cookies.json' in error for error in errors))

    def test_audit_scans_encoded_private_values_without_echoing_them(self):
        from tools.audit_release import audit_tree
        secret = 'private-build-secret'
        (self.root/'app.bin').write_bytes(secret.encode('utf-16-le'))
        errors = audit_tree(self.root, secrets=[secret])
        self.assertTrue(errors)
        self.assertNotIn(secret, '\n'.join(errors))

    def test_source_staging_ignores_unlisted_local_data(self):
        from tools.build_release import stage_source
        source = Path(__file__).resolve().parents[1]
        stage = self.root/'source'
        stage_source(source, stage)
        self.assertTrue((stage/'app.py').is_file())
        self.assertTrue((stage/'config.example.ini').is_file())
        self.assertFalse((stage/'.env').exists())
        self.assertFalse((stage/'RunCourseEvaluation.exe').exists())
        self.assertFalse((stage/'docs/superpowers').exists())

    def test_audit_accepts_blank_config_template(self):
        from tools.audit_release import audit_tree
        (self.root/'config.ini').write_text('[user-account]\nusername=\npassword=\n[evaluation-option]\nsubmit=false\n')
        self.assertEqual(audit_tree(self.root), [])

    def test_source_provenance_works_without_git_and_detects_edited_archive(self):
        from tools.build_release import source_provenance
        source = self.root/'app.py'
        source.write_bytes(b'print("source")\n')
        metadata = {'source_commit': 'a'*40, 'source_dirty': False,
                    'source_files_sha256': {'app.py': hashlib.sha256(source.read_bytes()).hexdigest()}}
        (self.root/'SOURCE-INFO.json').write_text(json.dumps(metadata))
        result = source_provenance(self.root)
        self.assertEqual(result['source_commit'], 'a'*40)
        self.assertFalse(result['source_dirty'])
        source.write_bytes(b'print("edited")\n')
        self.assertTrue(source_provenance(self.root)['source_dirty'])

    def test_short_build_directory_keeps_friendly_archive_root(self):
        from tools.build_release import archive_tree
        stage = self.root/'app'
        stage.mkdir()
        (stage/'readme.txt').write_text('Public file')
        archive = self.root/'release.zip'
        archive_tree(stage, archive, root_name='JiaoyiCourseEvaluation-v0.1.0-windows-x64')
        with zipfile.ZipFile(archive) as bundle:
            self.assertEqual(bundle.namelist(), ['JiaoyiCourseEvaluation-v0.1.0-windows-x64/readme.txt'])


if __name__ == '__main__':
    unittest.main()
