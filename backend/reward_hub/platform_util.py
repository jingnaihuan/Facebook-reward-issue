# -*- coding: utf-8 -*-
"""跨平台系统交互层：平台判断、Python 命令探测、原生「另存为」对话框。

把所有 OS 相关分支都收在这里，好处：
  1) server.py 只调用平台无关的接口，不再散落 osascript/平台判断。
  2) 纯函数便于在 Mac 上用 monkeypatch 模拟 Windows 做单元测试。
"""
import os
import sys
import shutil
import subprocess


def is_windows():
    return os.name == "nt"


def is_mac():
    return sys.platform == "darwin"


def detect_python_cmd():
    """当前系统上最合适的 Python 启动命令（供启动脚本 / 文档 / 诊断参考）。

    Windows 优先 py（官方 Python launcher），退而求其次 python；
    类 Unix 用 python3。仅按可执行文件是否存在判断，都找不到时给回退默认值。
    """
    if is_windows():
        for cmd in ("py", "python", "python3"):
            if shutil.which(cmd):
                return cmd
        return "python"
    for cmd in ("python3", "python"):
        if shutil.which(cmd):
            return cmd
    return "python3"


# ── 原生「另存为」对话框 ──────────────────────────────────────────────
# choose_save_path 返回 (kind, path)：
#   ok       用户选定路径（已保证 .xlsx 结尾）
#   cancel   用户主动取消
#   fallback 当前环境没有可用的原生对话框，交由调用方落到默认工作区


def _choose_save_path_mac(default_name, prompt):
    """macOS 原生「存储」对话框（osascript）。"""
    safe = default_name.replace('"', "").replace("\\", "")
    script = ('set theFile to choose file name with prompt "%s" default name "%s"\n'
              "POSIX path of theFile" % (prompt, safe))
    try:
        proc = subprocess.run(["osascript", "-e", script],
                              capture_output=True, text=True, timeout=300)
    except Exception:
        return ("fallback", None)
    out = (proc.stdout or "").strip()
    if proc.returncode == 0 and out:
        return ("ok", out)
    return ("cancel", None)          # 用户点了取消，或对话框异常


def _win_save_dialog(default_name, prompt):
    """真正调起 Windows 上的 tkinter 保存框；隔离在此以便单测替身。

    返回：选定路径字符串 / 空字符串（取消）；tkinter 不可用则抛异常。
    """
    import tkinter
    from tkinter import filedialog
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        path = filedialog.asksaveasfilename(
            title=prompt,
            initialfile=default_name,
            defaultextension=".xlsx",
            filetypes=[("Excel 工作簿", "*.xlsx"), ("所有文件", "*.*")])
    finally:
        root.destroy()
    return path or ""


def _choose_save_path_windows(default_name, prompt):
    """Windows：tkinter（Python 自带）原生「另存为」；tk 缺失则回退。"""
    try:
        path = _win_save_dialog(default_name, prompt)
    except Exception:
        return ("fallback", None)      # 精简版 Python 未装 tk 等
    if path:
        return ("ok", path)
    return ("cancel", None)


def choose_save_path(default_name, prompt="保存发奖名单"):
    """按平台弹原生保存框。见上方 (kind, path) 约定。"""
    if is_mac():
        kind, path = _choose_save_path_mac(default_name, prompt)
    elif is_windows():
        kind, path = _choose_save_path_windows(default_name, prompt)
    else:
        kind, path = ("fallback", None)
    if kind == "ok" and path and not path.lower().endswith(".xlsx"):
        path += ".xlsx"
    return (kind, path)
