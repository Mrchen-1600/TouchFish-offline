# -*- mode: python ; coding: utf-8 -*-
import sys
import os
import glob
import site
import vosk
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
base_dir = os.getcwd() # 获取当前工作目录

# --- 1. 获取 vosk 库的物理路径 ---
vosk_path = os.path.dirname(vosk.__file__)

# --- 2. 自动搜索 dlib 核心文件 ---
dlib_binaries = []
# 获取当前环境的 site-packages 路径
site_packages = site.getsitepackages()[1]
# 搜索该目录下的 pyd 文件
pyd_files = glob.glob(os.path.join(site_packages, '_dlib_pybind11*.pyd'))

if pyd_files:
    print(f"Found dlib binary: {pyd_files[0]}")
    # 格式: (源文件路径, 打包后的目标目录)
    # 注意：目标目录必须是 '.' (根目录)，否则 import 找不到
    dlib_binaries = [(pyd_files[0], '.')]
else:
    print("WARNING: Cound not find _dlib_pybind11*.pyd! Please ensure you copied it.")


# 3. 自动收集 face_recognition_models 里的所有 .dat 模型文件
face_models = collect_data_files('face_recognition_models')

# 4. 手动添加我们自己的资源
# 格式: (源路径, 目标路径)
my_datas = [
    ('modules', 'modules'),    # 打包 modules 文件夹
    ('model', 'model'),        # 打包 vosk 语音模型文件夹
    ('logo.ico', '.'),         # 打包图标文件
    (vosk_path, 'vosk'),
]

# 5. 合并所有资源列表
all_datas = my_datas + face_models

# --- 6.排除不需要的库 ---
# 这些库通常体积很大，但摸鱼神器用不到
excluded_modules = [
    'matplotlib', 'scipy', 'pandas', 'bokeh', 'plotly', 'triton', # 数据分析绘图类
    'unittest', 'difflib', 'doctest', # 测试类
    'tkinter.test',
    'pydoc',
]


hidden_imports = [
    'face_recognition',
    'face_recognition_models',
    'cv2',
    'numpy',
    'pyaudio',
    'PIL',
    'PIL.ImageTk',
    'dlib',
    # 配合上面的 binaries 物理文件，双管齐下
    '_dlib_pybind11',
]

a = Analysis(
    ['main_gui.py'],
    pathex=[base_dir],
    binaries=dlib_binaries,  # 加上 dlib 的二进制文件
    datas=all_datas,           # 使用合并后的列表
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TouchFish',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='logo.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TouchFish',
)