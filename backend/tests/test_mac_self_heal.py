# -*- coding: utf-8 -*-
"""Mac 自愈 + 分离式后台服务（app_entry）的单元测试。

覆盖发奖中台在 macOS 上曾出现的两类"打开失败"根因的修复：
- App Translocation（下载后带 quarantine、adhoc 未签名 → 只读挂载运行 → 再开报 -47）；
- 常驻挂起进程 + LSUIElement + os._exit 硬杀 → LaunchServices 陈旧记录 →
  再点弹「The application "RewardHub" is not open anymore.」。

修复策略（移植 LocoFlow 已验证方案）：
- `_mac_self_heal`：检测 translocation → 去真实副本 quarantine → 排队在本实例退出后重开真实副本；
- 启动器 / 独立后台服务分离（`--serve`）：双击只跑启动器，服务作独立进程存活，启动器随即退出。

不触碰 Playwright / 真实浏览器 / 真实签名。
"""
import os
import sys
import types
import subprocess


def _import_app_entry():
    pkg_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "packaging")
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)
    import app_entry
    return app_entry


# ── _own_app_bundle：从可执行路径回推 .app 根 ──────────────────────
def test_own_app_bundle_recovers_root():
    ae = _import_app_entry()
    exe = "/Apps/RewardHub.app/Contents/MacOS/RewardHub"
    assert ae._own_app_bundle(exe) == "/Apps/RewardHub.app"


def test_own_app_bundle_none_for_plain_exe():
    ae = _import_app_entry()
    assert ae._own_app_bundle("/usr/local/bin/python3") is None


def test_own_app_bundle_none_when_prefix_not_dot_app():
    ae = _import_app_entry()
    # 有 /Contents/MacOS/ 但其前缀不以 .app 结尾 → 不是标准 bundle
    assert ae._own_app_bundle("/x/foo/Contents/MacOS/foo") is None


# ── _translocated_original：只读挂载 → 真实 .app 路径（读 mount 表）─
def test_translocated_original_none_when_not_translocated():
    ae = _import_app_entry()
    assert ae._translocated_original("/Apps/RewardHub.app/Contents/MacOS/RewardHub") is None


def test_translocated_original_maps_via_mount(monkeypatch):
    ae = _import_app_entry()
    exe = ("/private/var/folders/aa/AppTranslocation/ABC-123/d/"
           "RewardHub.app/Contents/MacOS/RewardHub")
    mount_out = (
        "/dev/disk1s1 on / (apfs, local)\n"
        "/Users/me/Downloads/RewardHub.app on "
        "/private/var/folders/aa/AppTranslocation/ABC-123 (nullfs, local, nodev, nosuid, read-only)\n"
    )
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(stdout=mount_out))
    assert ae._translocated_original(exe) == "/Users/me/Downloads/RewardHub.app"


def test_translocated_original_none_when_no_matching_mount(monkeypatch):
    ae = _import_app_entry()
    exe = "/private/var/folders/aa/AppTranslocation/ZZZ-999/d/RewardHub.app/Contents/MacOS/RewardHub"
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(stdout="/dev/disk1s1 on / (apfs, local)\n"))
    assert ae._translocated_original(exe) is None


# ── _mac_self_heal：去隔离 + 排队重开 ──────────────────────────────
def test_mac_self_heal_noop_for_plain_exe(monkeypatch):
    ae = _import_app_entry()
    monkeypatch.setattr(sys, "executable", "/usr/local/bin/python3")
    calls = {"run": 0, "popen": 0}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.__setitem__("run", calls["run"] + 1))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.__setitem__("popen", calls["popen"] + 1))
    # 既非 translocation、又非 .app 结构 → 不去隔离、不重开
    assert ae._mac_self_heal() is False
    assert calls["popen"] == 0


def test_mac_self_heal_dequarantines_and_schedules_reopen(monkeypatch, tmp_path):
    ae = _import_app_entry()
    app = tmp_path / "RewardHub.app"
    app.mkdir()
    exe = str(app) + "/Contents/MacOS/RewardHub"   # 语义上跑在 translocation 里
    monkeypatch.setattr(sys, "executable",
                        "/private/var/folders/aa/AppTranslocation/ABC/d/RewardHub.app/Contents/MacOS/RewardHub")
    monkeypatch.setattr(ae, "_translocated_original", lambda e: str(app))
    seen = {}
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, *a, **k: seen.__setitem__("xattr", cmd))
    monkeypatch.setattr(subprocess, "Popen",
                        lambda cmd, *a, **k: seen.__setitem__("reopen", cmd))
    assert ae._mac_self_heal() is True
    assert seen["xattr"][:3] == ["xattr", "-dr", "com.apple.quarantine"]
    assert seen["xattr"][3] == str(app)
    assert seen["reopen"][0] == "/bin/sh" and "open" in seen["reopen"][2]


def test_mac_self_heal_dequarantines_real_path_without_reopen(monkeypatch, tmp_path):
    ae = _import_app_entry()
    app = tmp_path / "RewardHub.app"
    app.mkdir()
    monkeypatch.setattr(sys, "executable", str(app) + "/Contents/MacOS/RewardHub")
    seen = {"popen": 0}
    monkeypatch.setattr(subprocess, "run", lambda cmd, *a, **k: seen.__setitem__("xattr", cmd))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: seen.__setitem__("popen", seen["popen"] + 1))
    # 从真实路径运行但带隔离：顺手去隔离，但不需重开 → 返回 False、不 Popen
    assert ae._mac_self_heal() is False
    assert seen["xattr"][3] == str(app)
    assert seen["popen"] == 0


# ── _spawn_detached_server：独立后台服务，抑制其自开浏览器 ──────────
def test_spawn_detached_sets_no_browser_env(monkeypatch, tmp_path):
    ae = _import_app_entry()
    from reward_hub import common
    monkeypatch.setattr(common, "app_data_dir", lambda: str(tmp_path))
    seen = {}
    monkeypatch.setattr(subprocess, "Popen",
                        lambda cmd, **k: seen.update(cmd=cmd, kw=k))
    ae._spawn_detached_server()
    assert seen["cmd"][-1] == "--serve"
    assert seen["kw"]["env"].get("REWARD_HUB_NO_BROWSER") == "1"
    if not sys.platform.startswith("win"):
        assert seen["kw"].get("start_new_session") is True


# ── main 分发：--serve 只跑服务 ────────────────────────────────────
def test_main_serve_runs_server_only(monkeypatch):
    ae = _import_app_entry()
    import server
    monkeypatch.setattr(sys, "argv", ["app_entry", "--serve"])
    from reward_hub import common
    monkeypatch.setattr(common, "force_utf8_std", lambda: None)
    called = {"server": 0, "mac": 0, "legacy": 0}
    monkeypatch.setattr(server, "main", lambda: called.__setitem__("server", called["server"] + 1))
    monkeypatch.setattr(ae, "_mac_launch", lambda: called.__setitem__("mac", 1))
    monkeypatch.setattr(ae, "_legacy_launch", lambda: called.__setitem__("legacy", 1))
    ae.main()
    assert called == {"server": 1, "mac": 0, "legacy": 0}


def test_main_darwin_uses_mac_launch(monkeypatch):
    ae = _import_app_entry()
    monkeypatch.setattr(sys, "argv", ["app_entry"])
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    called = {"mac": 0, "legacy": 0}
    monkeypatch.setattr(ae, "_mac_launch", lambda: called.__setitem__("mac", 1))
    monkeypatch.setattr(ae, "_legacy_launch", lambda: called.__setitem__("legacy", 1))
    ae.main()
    assert called == {"mac": 1, "legacy": 0}


def test_main_non_darwin_uses_legacy_launch(monkeypatch):
    ae = _import_app_entry()
    monkeypatch.setattr(sys, "argv", ["app_entry"])
    monkeypatch.setattr(sys, "platform", "win32")
    called = {"mac": 0, "legacy": 0}
    monkeypatch.setattr(ae, "_mac_launch", lambda: called.__setitem__("mac", 1))
    monkeypatch.setattr(ae, "_legacy_launch", lambda: called.__setitem__("legacy", 1))
    ae.main()
    assert called == {"mac": 0, "legacy": 1}
