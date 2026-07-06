# -*- coding: utf-8 -*-
"""验证服务退出清理：被追踪的下载子进程会被 _cleanup_jobs 终止，不残留后台进程。"""
import sys
import time
import subprocess

import server


def _spawn_sleeper():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def test_cleanup_terminates_tracked_subprocess():
    proc = _spawn_sleeper()
    server.JOBS["jt_cleanup"] = {"progress": [], "done": False, "result": None, "proc": proc}
    try:
        assert proc.poll() is None                # 子进程还活着
        server._cleanup_jobs()
        for _ in range(50):                        # 最多等 5s 让其退出
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        assert proc.poll() is not None             # 已被清理，不残留
    finally:
        if proc.poll() is None:
            proc.kill()
        server.JOBS.pop("jt_cleanup", None)


def test_cleanup_ignores_finished_and_none():
    """已结束的进程与 proc=None 不应报错。"""
    done = _spawn_sleeper()
    done.terminate()
    done.wait(timeout=5)
    server.JOBS["jt_done"] = {"proc": done}
    server.JOBS["jt_none"] = {"proc": None}
    try:
        server._cleanup_jobs()                     # 不抛异常即通过
    finally:
        server.JOBS.pop("jt_done", None)
        server.JOBS.pop("jt_none", None)
