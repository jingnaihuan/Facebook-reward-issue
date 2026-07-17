# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 配置：把 社群互动发奖中台 打包成 Mac .app / Windows onedir exe。
- 入口：packaging/app_entry.py
- 不内置 Chromium；但必须带 Playwright 的 Node driver（驱动系统 Chrome/Edge 的必需件）。
- frontend/ 作为数据目录打入；backend 作为源根加入 pathex。
从仓库根目录运行：  pyinstaller packaging/reward_hub.spec --noconfirm
"""
import os
import sys
from PyInstaller.utils.hooks import collect_all

# SPECPATH 是本 spec 所在目录(packaging/)，REPO 是仓库根。用绝对路径避免相对拼接出错。
SPEC_DIR = SPECPATH
REPO = os.path.dirname(SPEC_DIR)
ENTRY = os.path.join(SPEC_DIR, "app_entry.py")
BACKEND = os.path.join(REPO, "backend")
# 应用图标（奖杯 logo）：macOS 用 .icns，Windows 用 .ico。均由 packaging/icon.svg 生成。
ICON_ICNS = os.path.join(SPEC_DIR, "RewardHub.icns")
ICON_ICO = os.path.join(SPEC_DIR, "RewardHub.ico")

# Playwright 的 driver/数据文件必须全量收集，否则运行时找不到 driver（无法驱动系统浏览器）。
pw_datas, pw_binaries, pw_hidden = collect_all("playwright")
opx_datas, opx_binaries, opx_hidden = collect_all("openpyxl")

datas = [
    (os.path.join(REPO, "frontend"), "frontend"),   # server 冻结时从 _MEIPASS/frontend 读页面
]
datas += pw_datas + opx_datas
binaries = pw_binaries + opx_binaries
hiddenimports = pw_hidden + opx_hidden + [
    "server",
    "reward_hub",
    "reward_hub.common",
    "reward_hub.platform_util",
    "reward_hub.extract_id",
    "reward_hub.dedup",
    "reward_hub.language_filter",
    "reward_hub.rule_engine",
    "reward_hub.keyword",
    "reward_hub.export",
    "reward_hub.config_store",
    "reward_hub.eastblue_download",
    "reward_hub.eastblue_parse",
    "reward_hub.version",
    # Windows「另存为」用 tkinter（懒加载在函数内），显式列出确保被打入。
    "tkinter",
    "tkinter.filedialog",
]

a = Analysis(
    [ENTRY],
    pathex=[BACKEND],            # 让 `import server` / reward_hub 可解析
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RewardHub",
    console=False,               # 不弹黑色控制台窗口
    disable_windowed_traceback=False,
    icon=(ICON_ICNS if sys.platform == "darwin" else ICON_ICO),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="RewardHub",
)

# Mac 额外产出 .app bundle
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="RewardHub.app",
        icon=ICON_ICNS,
        bundle_identifier="com.yotta.rewardhub",
        info_plist={
            # 后台型工具：双击只是打开浏览器后就退出前台，没必要在 dock 占位 / 跳动。
            # LSUIElement=True 让 .app 不进 dock、不抢焦点，避免重复双击时 dock 一直跳。
            "LSUIElement": True,
        },
    )
