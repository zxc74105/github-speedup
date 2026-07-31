# -*- mode: python ; coding: utf-8 -*-

import os
import sys

_datas = [
    ('github_speedup', 'github_speedup'),
    ('main.py', '.'),
    ('proxies.json', '.'),
]

_binaries = []
if sys.platform == 'win32':
    _binaries.append(('bin/aria2c.exe', 'bin'))

_target_arch = os.environ.get('TARGET_ARCH') or None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=['tlclient', 'tls_client', 'tls_client.sessions'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
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
    argv_emulation=False,
    target_arch=_target_arch,
    codesign_identity=None,
    entitlements_file=None,
)
