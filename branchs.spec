# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# CLI executable analysis
cli_a = Analysis(
    ['branchs/cli.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'click',
        'rich',
        'rich.console',
        'rich.table',
        'rich.panel',
        'rich.text',
        'rich.syntax',
        'rich.tree',
        'git',
        'branchs',
        'branchs.core',
        'branchs.core.branch',
        'branchs.core.commit',
        'branchs.core.config',
        'branchs.core.git',
        'branchs.core.remote',
    ] + collect_submodules('rich') + collect_submodules('git'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

cli_pyz = PYZ(cli_a.pure, cli_a.zipped_data, cipher=block_cipher)

cli_exe = EXE(
    cli_pyz,
    cli_a.scripts,
    cli_a.binaries,
    cli_a.zipfiles,
    cli_a.datas,
    [],
    name='branchs',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# GUI executable analysis
gui_a = Analysis(
    ['branchs/gui.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.scrolledtext',
        'tkinter.filedialog',
        'rich',
        'git',
        'branchs',
        'branchs.core',
        'branchs.core.branch',
        'branchs.core.commit',
        'branchs.core.config',
        'branchs.core.git',
        'branchs.core.remote',
    ] + collect_submodules('rich') + collect_submodules('git'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

gui_pyz = PYZ(gui_a.pure, gui_a.zipped_data, cipher=block_cipher)

gui_exe = EXE(
    gui_pyz,
    gui_a.scripts,
    gui_a.binaries,
    gui_a.zipfiles,
    gui_a.datas,
    [],
    name='branchs-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
