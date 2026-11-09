# -*- mode: python ; coding: utf-8 -*-
"""Build the independent Windows x64 runtime; copy models/assets next to EXE."""
from pathlib import Path
from importlib.util import find_spec
from PyInstaller.utils.hooks import collect_all

source = Path(SPECPATH)
datas, binaries, hiddenimports = [], [], []
for package in ('ctranslate2', 'sentencepiece', 'winrt'):
    package_datas, package_binaries, package_imports = collect_all(package)
    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_imports)

# CTranslate2 needs the C++ runtime from the shared DLL search directory.
# A copy nested under winrt/Qt does not make it available to every extension.
# Use the redistributable already shipped by the pinned WinRT wheel, not a
# dependency on the build machine's system-wide Visual C++ installation.
winrt_directory = Path(next(iter(find_spec('winrt').submodule_search_locations)))
binaries.append((str(winrt_directory / 'msvcp140.dll'), '.'))

analysis = Analysis(
    [str(source / 'app.py')],
    pathex=[str(source)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PyQt6', 'PySide2'],
    noarchive=False,
    optimize=0,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name='k4f_chan',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(source / 'assets' / 'app.ico'),
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name='k4f_chan',
)
