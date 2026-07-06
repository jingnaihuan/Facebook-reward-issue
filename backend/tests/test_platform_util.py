# -*- coding: utf-8 -*-
"""跨平台系统交互层单测：平台判断、python 命令探测、保存对话框三平台分支、
以及子进程 UTF-8 中文解码契约。全部在 Mac 上即可运行，用 monkeypatch 模拟 Windows。"""
import json
import subprocess
import sys

import reward_hub.platform_util as pu


# ── detect_python_cmd ────────────────────────────────────────────────
def test_detect_python_windows_prefers_py(monkeypatch):
    monkeypatch.setattr(pu, "is_windows", lambda: True)
    monkeypatch.setattr(pu.shutil, "which", lambda c: r"C:\py.exe" if c == "py" else None)
    assert pu.detect_python_cmd() == "py"


def test_detect_python_windows_falls_to_python(monkeypatch):
    monkeypatch.setattr(pu, "is_windows", lambda: True)
    monkeypatch.setattr(pu.shutil, "which", lambda c: r"C:\python.exe" if c == "python" else None)
    assert pu.detect_python_cmd() == "python"


def test_detect_python_windows_none_defaults(monkeypatch):
    monkeypatch.setattr(pu, "is_windows", lambda: True)
    monkeypatch.setattr(pu.shutil, "which", lambda c: None)
    assert pu.detect_python_cmd() == "python"


def test_detect_python_unix_prefers_python3(monkeypatch):
    monkeypatch.setattr(pu, "is_windows", lambda: False)
    monkeypatch.setattr(pu.shutil, "which", lambda c: "/usr/bin/python3" if c == "python3" else None)
    assert pu.detect_python_cmd() == "python3"


def test_detect_python_unix_falls_to_python(monkeypatch):
    monkeypatch.setattr(pu, "is_windows", lambda: False)
    monkeypatch.setattr(pu.shutil, "which", lambda c: "/usr/bin/python" if c == "python" else None)
    assert pu.detect_python_cmd() == "python"


# ── macOS 保存对话框（osascript）─────────────────────────────────────
class _Proc:
    def __init__(self, rc, out):
        self.returncode = rc
        self.stdout = out


def test_mac_dialog_ok(monkeypatch):
    monkeypatch.setattr(pu.subprocess, "run", lambda *a, **k: _Proc(0, "/Users/x/名单\n"))
    assert pu._choose_save_path_mac("发奖.xlsx", "保存") == ("ok", "/Users/x/名单")


def test_mac_dialog_cancel(monkeypatch):
    monkeypatch.setattr(pu.subprocess, "run", lambda *a, **k: _Proc(1, ""))
    assert pu._choose_save_path_mac("发奖.xlsx", "保存") == ("cancel", None)


def test_mac_dialog_no_osascript(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError()
    monkeypatch.setattr(pu.subprocess, "run", boom)
    assert pu._choose_save_path_mac("发奖.xlsx", "保存") == ("fallback", None)


# ── Windows 保存对话框（tkinter，隔离 _win_save_dialog 做替身）────────
def test_win_dialog_ok(monkeypatch):
    monkeypatch.setattr(pu, "_win_save_dialog", lambda n, p: r"C:\Users\x\名单.xlsx")
    assert pu._choose_save_path_windows("发奖.xlsx", "保存") == ("ok", r"C:\Users\x\名单.xlsx")


def test_win_dialog_cancel(monkeypatch):
    monkeypatch.setattr(pu, "_win_save_dialog", lambda n, p: "")
    assert pu._choose_save_path_windows("发奖.xlsx", "保存") == ("cancel", None)


def test_win_dialog_no_tk(monkeypatch):
    def boom(n, p):
        raise ImportError("no tkinter")
    monkeypatch.setattr(pu, "_win_save_dialog", boom)
    assert pu._choose_save_path_windows("发奖.xlsx", "保存") == ("fallback", None)


# ── choose_save_path 分派 + .xlsx 归一化 ─────────────────────────────
def test_choose_dispatch_mac_appends_xlsx(monkeypatch):
    monkeypatch.setattr(pu, "is_mac", lambda: True)
    monkeypatch.setattr(pu, "is_windows", lambda: False)
    monkeypatch.setattr(pu, "_choose_save_path_mac", lambda n, p: ("ok", "/tmp/名单"))
    assert pu.choose_save_path("发奖.xlsx") == ("ok", "/tmp/名单.xlsx")


def test_choose_dispatch_windows(monkeypatch):
    monkeypatch.setattr(pu, "is_mac", lambda: False)
    monkeypatch.setattr(pu, "is_windows", lambda: True)
    monkeypatch.setattr(pu, "_choose_save_path_windows", lambda n, p: ("ok", r"C:\a\名单.xlsx"))
    assert pu.choose_save_path("发奖.xlsx") == ("ok", r"C:\a\名单.xlsx")


def test_choose_dispatch_linux_fallback(monkeypatch):
    monkeypatch.setattr(pu, "is_mac", lambda: False)
    monkeypatch.setattr(pu, "is_windows", lambda: False)
    assert pu.choose_save_path("发奖.xlsx") == ("fallback", None)


def test_choose_cancel_passthrough(monkeypatch):
    monkeypatch.setattr(pu, "is_mac", lambda: True)
    monkeypatch.setattr(pu, "is_windows", lambda: False)
    monkeypatch.setattr(pu, "_choose_save_path_mac", lambda n, p: ("cancel", None))
    assert pu.choose_save_path("发奖.xlsx") == ("cancel", None)


# ── 子进程 UTF-8 中文解码契约（守护 server.py 的编码修复）────────────
def test_subprocess_utf8_chinese_roundtrip():
    """复刻 server 读 Eastblue 子进程输出的方式：子进程按 common.emit 写 UTF-8 中文，
    父进程用 encoding='utf-8' 读回，中文不乱码且 JSON 可解析。
    这条测试在中文版 Windows（默认 cp936）上若丢了 encoding 参数会失败。"""
    code = (
        "import sys, json\n"
        "b = json.dumps({'progress': '正在按 3 个玩家ID搜索…'}, ensure_ascii=False).encode('utf-8')\n"
        "sys.stdout.buffer.write(b); sys.stdout.buffer.write(b'\\n'); sys.stdout.buffer.flush()\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1)
    line = proc.stdout.readline().strip()
    proc.wait()
    msg = json.loads(line)
    assert msg["progress"] == "正在按 3 个玩家ID搜索…"
