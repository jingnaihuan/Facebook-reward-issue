# -*- coding: utf-8 -*-
"""公共工具：数据目录、JSON 读写、子脚本 emit/log、打包(冻结)期进程/端口管理。"""
import os, sys, io, json


def is_frozen():
    """是否运行在 PyInstaller 打包产物里（.app / .exe）。冻结版跳过 pip 安装等开发期逻辑，
    且子脚本改由 `<exe> --run-script <name>` 分发（见 server.script_cmd / app_entry）。"""
    return bool(getattr(sys, "frozen", False))


def force_utf8_std():
    """把 sys.stdout / sys.stderr 强制成 UTF-8 文本流（错误回退 replace）。
    Windows 控制台/管道默认 cp936(GBK)，print()/log() 遇 emoji 或日韩字符会 UnicodeEncodeError 崩；
    冻结版(console=False) 子进程 stdout 可能为 None，这里一并重建。重复调用安全。"""
    for attr in ("stdout", "stderr"):
        s = getattr(sys, attr, None)
        if s is None:
            try:
                fd = 1 if attr == "stdout" else 2
                setattr(sys, attr, io.TextIOWrapper(io.BufferedWriter(io.FileIO(fd, "w")),
                                                    encoding="utf-8", errors="replace"))
            except Exception:
                pass
            continue
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def no_window_kwargs():
    """Windows 上无黑框 exe 调子进程(netstat/taskkill 等)会闪控制台窗，用 CREATE_NO_WINDOW 抑制。
    返回可解包进 subprocess 调用的 kwargs；其它平台为空。"""
    if sys.platform.startswith("win"):
        import subprocess
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def pids_on_port(port):
    """返回监听指定端口的进程 PID 集合（跨平台）。用于启动时杀旧后台。"""
    import subprocess
    pids = set()
    try:
        if sys.platform.startswith("win"):
            out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace",
                                 **no_window_kwargs()).stdout or ""
            for line in out.splitlines():
                if (":%d" % port) in line and "LISTENING" in line.upper():
                    pids.add(line.split()[-1])
        else:
            out = subprocess.run(["lsof", "-ti", "tcp:%d" % port, "-sTCP:LISTEN"],
                                 capture_output=True, text=True).stdout or ""
            pids.update(p for p in out.split() if p)
    except Exception:
        pass
    return {p for p in pids if p and p.isdigit()}


PID_FILE = os.path.join(os.path.expanduser("~/.reward_hub_app"), "server.pid")


def write_pid_file():
    """写当前进程 PID 到固定文件，供下次启动定位旧实例（端口检测被防火墙拦时兜底）。"""
    try:
        os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def read_old_pid():
    """读上次写入的 PID；不存在 / 非数字 / 非活跃进程 / 就是自己 返回 None。"""
    try:
        if not os.path.exists(PID_FILE):
            return None
        pid = int(open(PID_FILE).read().strip())
        if pid == os.getpid():
            return None
        if sys.platform.startswith("win"):
            import ctypes
            PROCESS_QUERY_LIMITED = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
            if not h:
                return None
            ctypes.windll.kernel32.CloseHandle(h)
            return pid
        os.kill(pid, 0)          # 不发信号，仅探测是否存活
        return pid
    except Exception:
        return None


def kill_pid(pid):
    """结束指定 PID（跨平台）。"""
    import subprocess
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, **no_window_kwargs())
        else:
            os.kill(int(pid), 9)
    except Exception:
        pass


def app_data_dir():
    d = os.path.expanduser("~/.reward_hub_app")
    os.makedirs(d, exist_ok=True)
    return d


def work_dir():
    d = os.path.expanduser("~/Documents/发奖中台工作区")
    os.makedirs(d, exist_ok=True)
    return d


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def emit(obj):
    """子脚本向 server 回一行 JSON。"""
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()


def log(tag, msg):
    print("[%s] %s" % (tag, msg), flush=True)
