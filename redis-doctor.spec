# PyInstaller spec for a single-file redis-doctor binary.
# Build:  pyinstaller redis-doctor.spec
# Output: dist/redis-doctor

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hidden = (
    collect_submodules("redis_doctor")
    + collect_submodules("typer")
    + collect_submodules("rich")
    + collect_submodules("redis")
)

a = Analysis(
    ["redis_doctor/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=[("rules/default.yml", "redis_doctor/rules")],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["textual", "fastapi", "uvicorn", "weasyprint"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="redis-doctor",
    debug=False,
    strip=False,
    upx=True,
    console=True,
)
