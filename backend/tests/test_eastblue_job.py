# -*- coding: utf-8 -*-
"""验证 server 的 Eastblue 后台任务：进度收集 + 结果解析（不依赖 Playwright）。"""
import openpyxl
import server


class _FakeProc:
    """模拟下载子进程：stdout 逐行吐进度 + 最终结果。"""
    def __init__(self, lines):
        self.stdout = iter(lines)

    def wait(self):
        return 0


def _make_xlsx(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["玩家ID", "语言", "服务器"])
    ws.append(["1052837435", "en", "S177"])
    p = tmp_path / "eb.xlsx"
    wb.save(str(p))
    return str(p)


def test_job_collects_progress_and_parses_players(tmp_path, monkeypatch):
    xlsx = _make_xlsx(tmp_path)
    lines = [
        '{"progress": "启动无窗口浏览器…"}\n',
        'noise line that is not json\n',
        '{"progress": "下载完成，正在解析玩家表…"}\n',
        '{"ok": true, "path": "%s"}\n' % xlsx,
    ]
    monkeypatch.setattr(server.subprocess, "Popen", lambda *a, **k: _FakeProc(lines))

    job_id = "job_test"
    server.JOBS[job_id] = {"progress": [], "done": False, "result": None}
    server._run_eastblue(job_id, "http://example/download")

    job = server.JOBS[job_id]
    assert job["done"] is True
    assert job["progress"] == ["启动无窗口浏览器…", "下载完成，正在解析玩家表…"]
    assert job["result"]["ok"] is True
    assert "1052837435" in job["result"]["players"]


def test_job_reports_failure(tmp_path, monkeypatch):
    lines = ['{"progress": "需要登录…"}\n', '{"ok": false, "error": "登录超时"}\n']
    monkeypatch.setattr(server.subprocess, "Popen", lambda *a, **k: _FakeProc(lines))

    job_id = "job_fail"
    server.JOBS[job_id] = {"progress": [], "done": False, "result": None}
    server._run_eastblue(job_id, "http://example/download")

    job = server.JOBS[job_id]
    assert job["done"] is True
    assert job["result"]["ok"] is False
    assert job["result"]["error"] == "登录超时"
