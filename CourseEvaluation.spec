# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [('config.example.ini', '.')]
datas += collect_data_files('selenium')
datas += collect_data_files('ddddocr')
a = Analysis(['app.py'], pathex=[], binaries=[], datas=datas,
             hiddenimports=collect_submodules('ddddocr') + collect_submodules('selenium'),
             excludes=['tkinter', 'pytest', 'matplotlib', 'IPython'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='RunCourseEvaluation',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='RunCourseEvaluation')
