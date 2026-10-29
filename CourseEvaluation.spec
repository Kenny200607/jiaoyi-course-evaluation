# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from pathlib import Path
import ssl

datas = [('config.example.ini', '.')]
# Some Python distributions ship an additional certificate policy used by ssl.py.
# Preserve that policy in frozen applications rather than changing TLS verification.
certificate_policy = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
if certificate_policy.is_file():
    datas.append((str(certificate_policy), '.'))
datas += collect_data_files('selenium')
datas += collect_data_files('ddddocr')
a = Analysis(['app.py'], pathex=[], binaries=[], datas=datas,
             hiddenimports=collect_submodules('ddddocr') + collect_submodules('selenium'),
             excludes=['tkinter', 'pytest', 'matplotlib', 'IPython'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='RunCourseEvaluation',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='RunCourseEvaluation')
