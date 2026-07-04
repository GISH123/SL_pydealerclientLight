# pydealerLight_httpapi.spec
# -*- mode: python ; coding: utf-8 -*-

import os
import sys
import shutil
import subprocess

block_cipher = None

project_root = os.getcwd()
version_file = os.path.join(project_root, "version.txt")
crt_file = os.path.join(project_root, "server.crt")
key_file = os.path.join(project_root, "server.key")

# --------------------------------------------------
# 1锔忊儯 Increment version.txt  (KEEP OLD WORKING LOGIC)
# --------------------------------------------------

def increment_version(ver):
    parts = ver.strip().split("_")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
    except:
        parts.append("1")
    return "_".join(parts)

if os.path.exists(version_file):
    with open(version_file, "r", encoding="utf-8") as f:
        version = f.read().strip()

    new_version = increment_version(version)

    with open(version_file, "w", encoding="utf-8") as f:
        f.write(new_version)

    print(f"[SPEC] version incremented: {version} -> {new_version}")

else:
    new_version = "v1_0_0"
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(new_version)

    print("[SPEC] version.txt created:", new_version)

# --------------------------------------------------
# 2锔忊儯 Generate HTTPS cert/key for every build
#    (NEW, but does NOT remove old behavior)
# --------------------------------------------------

print("[SPEC] generating HTTPS certificate for this release...")

subprocess.run(
    [sys.executable, "generate_https_cert.py"],
    check=True,
    cwd=project_root
)

if not os.path.exists(crt_file) or not os.path.exists(key_file):
    raise RuntimeError("[SPEC] HTTPS certificate generation failed: server.crt/server.key missing")

print(f"[SPEC] HTTPS cert ready: {crt_file}")
print(f"[SPEC] HTTPS key ready:  {key_file}")

# --------------------------------------------------
# 3锔忊儯 Build name uses version  (KEEP OLD WORKING LOGIC)
# --------------------------------------------------

app_name = f"pydealerLight_httpapi_{new_version}"

# --------------------------------------------------
# 4锔忊儯 PyInstaller analysis
#    Only add cert/key to datas; keep old working settings
# --------------------------------------------------

a = Analysis(
    ['main.py'],
    pathex=[project_root],
    binaries=[],
    datas=[
        ('version.txt', '.'),
        ('server.crt', '.'),
        ('server.key', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name=app_name,
)

# --------------------------------------------------
# 5锔忊儯 Force version.txt / cert / key into dist root
#    version.txt copy is KEEP OLD WORKING LOGIC
#    cert/key copy is NEW
# --------------------------------------------------

dist_root = os.path.join("dist", app_name)
dst_version = os.path.join(dist_root, "version.txt")

try:
    shutil.copy(version_file, dst_version)
    print(f"[SPEC] version.txt copied to dist root: {dst_version}")
except Exception as e:
    print(f"[SPEC] version.txt copy failed: {e}")
