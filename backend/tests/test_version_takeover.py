# -*- coding: utf-8 -*-
"""版本感知的启动接管（修复：更新 exe 后旧后台仍在跑 → 新版被静默沿用）。

核心：启动器只在『线上服务版本 == 当前 exe 版本』时才复用旧后台；
版本不符 / 旧版无 version 字段 / 无服务，都要杀旧重起。
只测决策与分支，不碰真实网络 / 子进程 / 浏览器（沿用现有 monkeypatch 模式）。
"""
import os
import sys

from reward_hub.version import VERSION


def _import_app_entry():
    pkg_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "packaging")
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)
    import app_entry
    return app_entry


# ── 单一版本源一致性 ───────────────────────────────────────────────
def test_version_single_source_shared():
    ae = _import_app_entry()
    import server
    assert ae.VERSION == server.VERSION == VERSION
    assert isinstance(VERSION, str) and VERSION


# ── _should_reuse 决策矩阵 ─────────────────────────────────────────
def test_reuse_only_when_alive_and_same_version():
    ae = _import_app_entry()
    assert ae._should_reuse(True, VERSION, VERSION) is True


def test_no_reuse_when_version_differs():
    ae = _import_app_entry()
    assert ae._should_reuse(True, "0.0-old", VERSION) is False


def test_no_reuse_when_old_service_has_no_version():
    # 老版本 /api/ping 不带 version 字段 → running_version=None → 判为旧、需接管
    ae = _import_app_entry()
    assert ae._should_reuse(True, None, VERSION) is False


def test_no_reuse_when_no_service():
    ae = _import_app_entry()
    assert ae._should_reuse(False, None, VERSION) is False


# ── _mac_launch 分支 ───────────────────────────────────────────────
def _mac_calls(monkeypatch, ae, probe_ret):
    monkeypatch.setattr(ae, "_probe", lambda: probe_ret)
    calls = {"kill": 0, "spawn": 0, "open": 0}
    monkeypatch.setattr(ae, "_kill_old", lambda: calls.__setitem__("kill", calls["kill"] + 1))
    monkeypatch.setattr(ae, "_spawn_detached_server", lambda: calls.__setitem__("spawn", calls["spawn"] + 1))
    monkeypatch.setattr(ae, "_wait_ready", lambda *a, **k: True)
    monkeypatch.setattr(ae, "_open_browser", lambda: calls.__setitem__("open", calls["open"] + 1))
    ae._mac_launch()
    return calls


def test_mac_launch_reuses_same_version(monkeypatch):
    ae = _import_app_entry()
    assert _mac_calls(monkeypatch, ae, (True, VERSION)) == {"kill": 0, "spawn": 0, "open": 1}


def test_mac_launch_takes_over_stale_version(monkeypatch):
    ae = _import_app_entry()
    assert _mac_calls(monkeypatch, ae, (True, "0.0-old")) == {"kill": 1, "spawn": 1, "open": 1}


def test_mac_launch_starts_fresh_when_no_service(monkeypatch):
    ae = _import_app_entry()
    assert _mac_calls(monkeypatch, ae, (False, None)) == {"kill": 1, "spawn": 1, "open": 1}


# ── _legacy_launch（Windows，就是本次 bug 现场）分支 ────────────────
def test_legacy_launch_reuses_same_version(monkeypatch):
    """版本一致：只开浏览器、不杀旧、不起新（快速返回，无阻塞循环）。"""
    ae = _import_app_entry()
    monkeypatch.setattr(ae, "_probe", lambda: (True, VERSION))
    calls = {"kill": 0, "open": 0}
    monkeypatch.setattr(ae, "_kill_old", lambda: calls.__setitem__("kill", 1))
    monkeypatch.setattr(ae, "_open_browser", lambda: calls.__setitem__("open", 1))
    ae._legacy_launch()
    assert calls == {"kill": 0, "open": 1}


def test_legacy_launch_takes_over_stale_version(monkeypatch):
    """版本不符：杀旧 + 起新（这正是『更新后旧后台还在』的修复）。"""
    ae = _import_app_entry()
    import server
    monkeypatch.setattr(ae, "_probe", lambda: (True, "0.0-old"))
    calls = {"kill": 0, "open": 0}
    monkeypatch.setattr(ae, "_kill_old", lambda: calls.__setitem__("kill", calls["kill"] + 1))
    monkeypatch.setattr(server, "main", lambda: None)          # 别真起 HTTPServer
    monkeypatch.setattr(ae, "_wait_ready", lambda *a, **k: True)
    monkeypatch.setattr(ae, "_open_browser", lambda: calls.__setitem__("open", 1))
    # 收尾是 while True: time.sleep(3600)；让首个 sleep 抛 KeyboardInterrupt 以退出（函数已 catch）
    def _boom(*a, **k):
        raise KeyboardInterrupt()
    monkeypatch.setattr(ae.time, "sleep", _boom)
    ae._legacy_launch()
    assert calls["kill"] == 1 and calls["open"] == 1   # kill 只在接管分支调用，唯一标识
