# -*- coding: utf-8 -*-
"""打包(冻结)支持逻辑的单元测试：
- 子脚本命令在 开发 / 冻结 两种模式下的构造（server._eastblue_cmd）
- 看门狗心跳判定（server._touch_alive / _watchdog_expired）
- 冻结感知的前端路径（server.FRONTEND 指向真实 index.html）
- 进程/端口/PID 工具（reward_hub.common）
- eastblue_download.main(argv) 的入口契约（供 --run-script 分发）
- 打包入口 app_entry 的关键常量与分发判定
不触碰 Playwright / 真实浏览器。
"""
import os
import sys
import time

import server
from reward_hub import common
from reward_hub import eastblue_download


# ── server._eastblue_cmd：开发 vs 冻结 ──────────────────────────────
def test_eastblue_cmd_dev_mode(monkeypatch):
    monkeypatch.setattr(common, "is_frozen", lambda: False)
    cmd = server._eastblue_cmd("http://eb/download", "/tmp/ids.txt", "/tmp/out")
    assert cmd[0] == sys.executable
    assert cmd[1].endswith(os.path.join("reward_hub", "eastblue_download.py"))
    assert "--run-script" not in cmd
    assert cmd[2:] == ["--url", "http://eb/download",
                       "--ids-file", "/tmp/ids.txt", "--outdir", "/tmp/out"]


def test_eastblue_cmd_frozen_mode(monkeypatch):
    monkeypatch.setattr(common, "is_frozen", lambda: True)
    cmd = server._eastblue_cmd("http://eb/download", "/tmp/ids.txt", "/tmp/out")
    # 冻结版靠自我重入：<exe> --run-script eastblue ...，绝不能再拼 .py 路径
    assert cmd[0] == sys.executable
    assert cmd[1] == "--run-script"
    assert cmd[2] == "eastblue"
    assert not any(str(x).endswith(".py") for x in cmd)
    assert "--url" in cmd and "http://eb/download" in cmd
    assert "--outdir" in cmd and "/tmp/out" in cmd


# ── 看门狗心跳判定 ─────────────────────────────────────────────────
def test_touch_alive_updates_timestamp():
    server._last_alive[0] = 0.0
    server._touch_alive()
    assert time.time() - server._last_alive[0] < 2


def test_watchdog_not_expired_right_after_touch(monkeypatch):
    monkeypatch.setattr(server, "_any_job_active", lambda: False)
    server._touch_alive()
    assert server._watchdog_expired(time.time()) is False


def test_watchdog_expires_past_grace(monkeypatch):
    monkeypatch.setattr(server, "_any_job_active", lambda: False)
    server._touch_alive()
    stale = time.time() + server.WATCHDOG_GRACE + 5   # 模拟超过宽限期后再判定
    assert server._watchdog_expired(stale) is True


def test_watchdog_never_expires_while_download_active(monkeypatch):
    # 有下载任务在跑时，即便心跳早已超过宽限期，也绝不判过期（防误杀下载子进程）。
    monkeypatch.setattr(server, "_any_job_active", lambda: True)
    server._last_alive[0] = 0.0
    stale = time.time() + server.WATCHDOG_GRACE + 10_000
    assert server._watchdog_expired(stale) is False


def test_any_job_active_reflects_jobs(monkeypatch):
    monkeypatch.setattr(server, "JOBS", {})
    assert server._any_job_active() is False
    server.JOBS["j_running"] = {"done": False}
    assert server._any_job_active() is True
    server.JOBS["j_running"]["done"] = True
    assert server._any_job_active() is False


def test_watchdog_grace_is_generous():
    # 至少覆盖后台标签被降频到 1/分钟的情况（≥ 3 分钟余量）。
    assert server.WATCHDOG_GRACE >= 180


# ── 前端路径 ───────────────────────────────────────────────────────
def test_frontend_index_exists_dev():
    idx = os.path.join(server.FRONTEND, "index.html")
    assert os.path.isfile(idx), "开发模式下 FRONTEND 应指向仓库 frontend/index.html"


# ── reward_hub.common 进程/端口/编码工具 ───────────────────────────
def test_is_frozen_false_in_dev():
    assert common.is_frozen() is False


def test_no_window_kwargs_empty_on_posix():
    if sys.platform.startswith("win"):
        assert "creationflags" in common.no_window_kwargs()
    else:
        assert common.no_window_kwargs() == {}


def test_pids_on_port_returns_digit_set():
    pids = common.pids_on_port(59999)     # 极可能无人监听的高端口
    assert isinstance(pids, set)
    assert all(p.isdigit() for p in pids)


def test_read_old_pid_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(common, "PID_FILE", str(tmp_path / "nope.pid"))
    assert common.read_old_pid() is None


def test_write_then_read_own_pid_returns_none(monkeypatch, tmp_path):
    # 写入的就是自己，read_old_pid 应返回 None（不会把自己当旧实例杀）
    monkeypatch.setattr(common, "PID_FILE", str(tmp_path / "server.pid"))
    common.write_pid_file()
    assert os.path.isfile(common.PID_FILE)
    assert int(open(common.PID_FILE).read().strip()) == os.getpid()
    assert common.read_old_pid() is None


def test_force_utf8_std_idempotent():
    common.force_utf8_std()
    common.force_utf8_std()    # 重复调用不报错即通过


# ── eastblue_download.main 入口契约 ────────────────────────────────
def test_eastblue_main_no_ids_emits_error(monkeypatch):
    captured = {}
    monkeypatch.setattr(eastblue_download, "emit", lambda o: captured.update(o))
    # 有 --url 但无任何 ID → 立刻 emit 错误并返回 0，绝不进入 download/Playwright
    rc = eastblue_download.main(["--url", "http://eb", "--ids", "   "])
    assert rc == 0
    assert captured.get("ok") is False
    assert "玩家ID" in captured.get("error", "")


def test_eastblue_main_routes_ids_to_download(monkeypatch):
    calls = {}
    monkeypatch.setattr(eastblue_download, "download",
                        lambda url, ids, outdir: calls.update(url=url, ids=ids, outdir=outdir))
    rc = eastblue_download.main(
        ["--url", "http://eb", "--ids", "1052837435, 1093454463 1052837435", "--outdir", "/tmp/rh_out"])
    assert rc == 0
    assert calls["url"] == "http://eb"
    assert calls["ids"] == ["1052837435", "1093454463"]   # 去重 + 保序
    assert calls["outdir"] == "/tmp/rh_out"


# ── 打包入口 app_entry ─────────────────────────────────────────────
def _import_app_entry():
    pkg_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "packaging")
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)
    import app_entry
    return app_entry


def test_app_entry_open_url_uses_localhost():
    ae = _import_app_entry()
    # 浏览器地址必须是 localhost（FB 登录只认应用域名 localhost），健康检查用 127.0.0.1
    assert ae.OPEN_URL.startswith("http://localhost:")
    assert ae.PING_BASE.startswith("http://127.0.0.1:")
    assert ae.PORT == server.PORT == 8765


def test_app_entry_script_module_map():
    ae = _import_app_entry()
    assert ae._SCRIPT_MODULES["eastblue"] == "reward_hub.eastblue_download"


def test_app_entry_dispatch_noop_when_not_run_script(monkeypatch):
    ae = _import_app_entry()
    monkeypatch.setattr(sys, "argv", ["app_entry"])
    assert ae._dispatch_script() is False
