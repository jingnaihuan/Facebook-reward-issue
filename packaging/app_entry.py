# -*- coding: utf-8 -*-
"""
社群互动发奖中台 — 打包入口（PyInstaller 的 entry）。

职责：
1) 正常启动（双击 app）：
   · Mac：先"自愈"——若发现自己被 Gatekeeper 以 App Translocation 只读方式运行
     （下载后带 quarantine、又是 adhoc 未签名的典型状态；会导致再次打开报 -47，或因
     LSUIElement 常驻进程被看门狗 os._exit 硬杀后 LaunchServices 留下陈旧记录，再点弹
     「The application "RewardHub" is not open anymore.」），就去掉真实副本的隔离标记并
     从真实路径重开；然后确保后台服务在跑、打开浏览器，启动器进程随即退出（服务作为独立
     后台进程存活，避免每次点击被 macOS 当"已在运行"而无反应）。
   · Windows：沿用原逻辑（重复双击本就会起新进程→探测到服务→重开浏览器，无 translocation/
     quarantine 问题）。
2) 后台服务进程（带 --serve）：只跑 backend/server.py 的 HTTPServer 并阻塞，
   由启动器以 `<exe> --serve` 拉起为独立后台进程；退出交给服务端看门狗（关网页无心跳超时）。
3) 冻结分发子脚本（带 --run-script <name>）：打包后无法用 `python 脚本.py` 跑 Playwright，
   server 会以 `<exe> --run-script eastblue [args...]` 重新调用本 exe，这里据 name 派发到对应脚本 main。

开发模式（python3 packaging/app_entry.py）同样可用。

★ 浏览器一律用 http://localhost（不是 127.0.0.1）打开：FB 方式 A 登录只认应用域名 localhost，用 IP 会被拦。
  健康检查 / 杀旧实例走 127.0.0.1（本机直连，不受该限制）。
"""
import os
import sys
import json
import time
import shlex
import threading
import subprocess
import webbrowser
import urllib.request

# 让 backend 包可被 import（开发模式）；冻结模式下 PyInstaller 已把它们打入。
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.normpath(os.path.join(_HERE, "..", "backend"))
if os.path.isdir(_BACKEND) and _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

PORT = 18765
PING_BASE = "http://127.0.0.1:%d" % PORT      # 本机健康检查 / shutdown（内部用，不给 FB）
OPEN_URL = "http://localhost:%d/" % PORT      # 打开给用户的地址（FB 登录只认 localhost）

from reward_hub.version import VERSION         # 单一版本源（_BACKEND 已在 sys.path 中）

# 是否抑制自动开浏览器（测试 / 预览器托管）。★ 必须在 main 改写 env 之前、于导入期捕获：
# 分离式后台服务由 _spawn_detached_server 以 REWARD_HUB_NO_BROWSER=1 拉起（阻止 server 自开、
# 由启动器统一开 localhost），若这里读实时 env 会把启动器自己的打开也误抑制掉。
_SUPPRESS_BROWSER = os.environ.get("REWARD_HUB_NO_BROWSER") == "1"


# ---------------------------------------------------------------- 冻结分发
_SCRIPT_MODULES = {
    "eastblue": "reward_hub.eastblue_download",
}


def _dispatch_script():
    """处理 `--run-script <name> [args...]`：派发到对应脚本的 main(argv)。
    返回 True 表示已处理（调用方应退出），False 表示非分发调用。"""
    if len(sys.argv) >= 3 and sys.argv[1] == "--run-script":
        from reward_hub import common
        common.force_utf8_std()      # 冻结版 console=False 时子进程 stdout 可能为 None / 非 UTF-8
        name = sys.argv[2]
        mod_path = _SCRIPT_MODULES.get(name)
        if not mod_path:
            sys.stderr.write("未知脚本: %s\n" % name)
            sys.exit(2)
        import importlib
        mod = importlib.import_module(mod_path)
        rc = mod.main(sys.argv[3:])   # 剩余参数交给该脚本的 main()
        sys.exit(rc or 0)
    return False


# ---------------------------------------------------------------- 正常启动
def _open_browser():
    if _SUPPRESS_BROWSER:
        return
    try:
        webbrowser.open(OPEN_URL)
    except Exception:
        pass


def _probe():
    """探测本机 18765 上的服务：返回 (是否在跑, 其版本或 None)。
    老版本 /api/ping 不带 version 字段 → 返回 (True, None)，会被判为「旧版」需接管。"""
    try:
        with urllib.request.urlopen(PING_BASE + "/api/ping", timeout=1) as r:
            if r.status != 200:
                return (False, None)
            data = json.loads(r.read().decode("utf-8") or "{}")
            return (True, data.get("version"))
    except Exception:
        return (False, None)


def _ping_alive():
    """旧后台是否还活着（不看版本）。保留兼容，内部统一走 _probe。"""
    return _probe()[0]


def _should_reuse(alive, running_version, my_version):
    """是否复用线上旧后台：仅当『有服务 且 版本与当前 exe 一致』。
    版本不符 / 旧版无 version 字段 / 无服务 → 一律 False（需杀旧重起），
    修复「更新 exe 后旧后台仍在、新版被静默沿用」。"""
    return bool(alive) and running_version == my_version


def _kill_old():
    """启动前先优雅关掉旧后台（防迭代残留 / 电脑盲用户不会手动关）。
    顺序：① /api/shutdown 自愿退出 → ② 端口仍占用则按 PID 杀 → ③ PID 文件兜底。最后轮询端口最多 4s。"""
    from reward_hub import common
    try:
        urllib.request.urlopen(PING_BASE + "/api/shutdown", timeout=2)
    except Exception:
        pass
    time.sleep(0.4)
    for pid in common.pids_on_port(PORT):
        common.kill_pid(pid)
    old = common.read_old_pid()
    if old:
        common.kill_pid(old)
    for _ in range(40):
        if not common.pids_on_port(PORT):
            return
        time.sleep(0.1)


def _wait_ready(tries=80):
    for _ in range(tries):
        try:
            urllib.request.urlopen(PING_BASE + "/api/ping", timeout=1)
            return True
        except Exception:
            time.sleep(0.25)
    return False


# ---------------------------------------------------------------- Mac 自愈
def _translocated_original(exe):
    """把 App Translocation 只读挂载路径映射回真实 .app 路径（读 mount 表）。找不到返回 None。
    exe 形如 /private/var/folders/.../AppTranslocation/<UUID>/d/RewardHub.app/Contents/MacOS/RewardHub；
    mount 行形如：<真实.app 路径> on <.../AppTranslocation/<UUID>> (nullfs, ...)。"""
    import re
    m = re.match(r"(.*/AppTranslocation/[^/]+)", exe)
    if not m:
        return None
    mountpoint = m.group(1)
    try:
        out = subprocess.run(["/sbin/mount"], capture_output=True, text=True).stdout or ""
    except Exception:
        return None
    for line in out.splitlines():
        if " on " not in line or "nullfs" not in line:
            continue
        src, rest = line.split(" on ", 1)
        mnt = rest.rsplit(" (", 1)[0]
        if mnt == mountpoint:
            return src.strip()
    return None


def _own_app_bundle(exe):
    """冻结产物正常运行时，从可执行文件路径回推自身 .app 根：
    /path/RewardHub.app/Contents/MacOS/RewardHub -> /path/RewardHub.app。非 .app 结构返回 None。"""
    marker = "/Contents/MacOS/"
    i = exe.find(marker)
    if i > 0 and exe[:i].endswith(".app"):
        return exe[:i]
    return None


def _mac_self_heal():
    """Mac 冻结产物专用自愈（返回 True 表示已安排干净重开、调用方应立即退出本实例）：
    - 若跑在 App Translocation 只读挂载里：去掉真实副本 quarantine，并安排在本实例退出后
      `open` 真实副本（用 sh 轮询等本 PID 退出，避免 LaunchServices 把即将退出的旧实例
      误当"已在运行"而只激活不新起）。
    - 若从真实路径运行但仍带 quarantine：顺手去掉，防下次被 translocate（不需重开）。
    去隔离是本工具未做付费签名的补偿：quarantine 一旦去除，Gatekeeper 不再拦、不再 translocate，
    从此双击直接从真实路径运行、不再报 -47 / not open anymore。"""
    exe = sys.executable or ""
    translocated = "/AppTranslocation/" in exe
    app = _translocated_original(exe) if translocated else _own_app_bundle(exe)
    if not app or not os.path.isdir(app):
        return False
    try:
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", app], capture_output=True)
    except Exception:
        pass
    if not translocated:
        return False
    try:
        sh = 'while kill -0 %d 2>/dev/null; do sleep 0.2; done; open %s' % (
            os.getpid(), shlex.quote(app))
        subprocess.Popen(["/bin/sh", "-c", sh], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False  # 重开失败则退回：让本(translocated)实例继续把服务起起来，不卡死用户


# ---------------------------------------------------------------- 分离式后台服务
def _spawn_detached_server():
    """把 backend server 作为独立后台进程拉起（`<exe> --serve`）：启动器随即退出、服务进程独活。
    这样每次双击都跑一遍启动器逻辑（探测→重开浏览器），不会因 macOS 把常驻进程当"已在运行"
    而点击无反应。★ 用 REWARD_HUB_NO_BROWSER=1 让服务别自开浏览器——统一由启动器开 localhost。"""
    from reward_hub import common
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--serve"]
    else:
        cmd = [sys.executable, os.path.abspath(__file__), "--serve"]
    env = dict(os.environ)
    env["REWARD_HUB_NO_BROWSER"] = "1"
    try:
        f = open(os.path.join(common.app_data_dir(), "server.out.log"), "a", buffering=1)
    except Exception:
        f = subprocess.DEVNULL
    kw = dict(stdout=f, stderr=f, env=env)
    if sys.platform.startswith("win"):
        DETACHED_PROCESS = 0x00000008
        kw["creationflags"] = DETACHED_PROCESS | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kw["start_new_session"] = True
    subprocess.Popen(cmd, **kw)


def _mac_launch():
    """Mac 启动器：线上后台若与当前版本一致就复用 → 打开浏览器；否则杀旧重起。"""
    alive, ver = _probe()
    if _should_reuse(alive, ver, VERSION):
        _open_browser()
        return
    _kill_old()                 # 旧版/残留后台先关掉，避免占用 18765 导致新版起不来
    _spawn_detached_server()
    if _wait_ready():
        _open_browser()
    else:
        sys.stderr.write("本地服务启动超时。\n")


def _legacy_launch():
    """Windows 启动器：线上后台若与当前版本一致就复用；否则杀旧重起（进程内起服务并前台挂起，
    退出交给服务端看门狗）。★ 版本判断修复：更新 exe 后旧后台仍在时不再静默沿用旧版。"""
    alive, ver = _probe()
    if _should_reuse(alive, ver, VERSION):
        _open_browser()
        return
    _kill_old()
    # 让 server 别自己开浏览器（下面由本入口统一开 localhost，避免双开）
    os.environ["REWARD_HUB_NO_BROWSER"] = "1"
    import server  # backend/server.py，暴露 main() 起 HTTPServer
    threading.Thread(target=server.main, daemon=True).start()
    if _wait_ready():
        _open_browser()
    else:
        sys.stderr.write("本地服务启动超时。\n")
    # 前台挂起；真正退出由服务端看门狗（关网页无心跳超时）触发。
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


def main():
    if _dispatch_script():
        return
    # 后台服务进程：只跑 server 并阻塞在此（由 _spawn_detached_server 拉起）
    if len(sys.argv) >= 2 and sys.argv[1] == "--serve":
        from reward_hub import common
        common.force_utf8_std()
        import server
        server.main()
        return
    if sys.platform == "darwin":
        # 冻结产物先自愈；已安排干净重开则退出本实例
        if getattr(sys, "frozen", False) and _mac_self_heal():
            return
        _mac_launch()
    else:
        _legacy_launch()


if __name__ == "__main__":
    main()
