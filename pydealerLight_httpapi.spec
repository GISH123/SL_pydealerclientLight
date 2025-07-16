# -*- mode: python ; coding: utf-8 -*-

import pathlib, shutil, os

# ─────────────────── Analysis ────────────────────
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[],                       # let us copy manually later
    hiddenimports=['tkinter', 'PIL.ImageTk'],
    hookspath=[], runtime_hooks=[], excludes=[],
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# ─────────────────── EXE  (standard) ─────────────
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='pydealerLight_httpapi',
    console=True,
    debug=False,
    strip=False,
    upx=True,
    # keep exclude_binaries = False   → PyInstaller makes one exe in root
)

# ─────────────────── COLLECT  – onedir folder ────
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,        # none, but include anyway
    strip=False,
    upx=True,
    name='pydealerLight_httpapi',
)

# ─────────────────── Post-step ───────────────────
dist_root     = pathlib.Path('dist')
onedir_folder = dist_root / coll.name
print(f'[[spec]] post-step for folder {onedir_folder}')

# 1) copy resources
shutil.copy2('config.xml', onedir_folder / 'config.xml')

(onedir_folder / 'models').mkdir(exist_ok=True)
shutil.copy2('models/videolist.xml', onedir_folder / 'models/videolist.xml')

# 2) remove duplicate exe that PyInstaller leaves in dist\
root_exe = dist_root / f'{exe.name}'
if root_exe.exists():
    print(f'[[spec]] removing duplicate root exe {root_exe}')
    root_exe.unlink()
