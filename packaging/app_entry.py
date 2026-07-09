# -*- coding: utf-8 -*-
"""
社群互动发奖中台 — 打包入口（PyInstaller 的 entry）。

两种职责：
1) 正常启动（无 --run-script）：请旧后台自愿退出 → 进程内起 HTTP 服务 → 等服务就绪 →
   用默认浏览器打开本地页面 → 前台挂起（真正退出交给服务端看门狗：关网页约 1.5 分钟后自动退）。
2) 冻结分发（带 --run-script <name>）：打包后无法用 `python 脚本.py` 跑 Playwright 子脚本，
   server 会以 `<exe> --run-script eastblue [args...]` 重新调用本 exe，这里据 name 派发到对应脚本 main。

开发模式（python3 packaging/app_entry.py）同样可用。

★ 浏览器一律用 http://localhost（不是 127.0.0.1）打开：FB 方式 A 登录只认应用域名 localhost，用 IP 会被拦。
  健康检查 / 杀旧实例走 127.0.0.1（本机直连，不受该限制）。
"""
import os
import sys
import time
import threading
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

# 是否抑制自动开浏览器（测试 / 预览器托管）。★ 必须在 main 改写 env 之前、于导入期捕获：
# main 会把 REWARD_HUB_NO_BROWSER=1 设给 server（阻止 server 自开、由本入口统一开），
# 若这里读实时 env 会把本入口自己的打开也误抑制掉。
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


def _ping_alive():
    """探测旧后台是否还活着；活着就别再起一个 server（双开会让浏览器多打一个标签页）。"""
    try:
        with urllib.request.urlopen(PING_BASE + "/api/ping", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


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


def main():
    if _dispatch_script():
        return
    if _ping_alive():
        # 已在运行——只打开浏览器并直接退出，避免残留多个 exe 进程 / 多开标签
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


if __name__ == "__main__":
    main()
