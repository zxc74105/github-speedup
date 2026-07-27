# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('proxies.json', '.')],
    hiddenimports=[
        'github_speedup',
        'github_speedup.core',
        'github_speedup.core.downloader',
        'github_speedup.core.proxy_manager',
        'github_speedup.core.settings',
        'github_speedup.core.utils',
        'github_speedup.core.logger',
        'github_speedup.core.records',
        'github_speedup.gui',
        'github_speedup.gui.main_window',
        'github_speedup.gui.download_page',
        'github_speedup.gui.proxy_page',
        'github_speedup.gui.settings_page',
        'github_speedup.server',
        'github_speedup.server.proxy_server',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'scipy', 'pandas', 'PIL',
        'cv2', 'tensorflow', 'torch', 'jupyter', 'ipython',
        'notebook', 'PyQt5', 'PyQt6',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='github-speedup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
)
