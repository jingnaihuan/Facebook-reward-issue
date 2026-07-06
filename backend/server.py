# -*- coding: utf-8 -*-
"""发奖中台本地服务（标准库 http.server，无框架）。"""
import os, sys, json, uuid, threading, subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from reward_hub import common
from reward_hub.extract_id import extract_id
from reward_hub.dedup import dedup
from reward_hub.language_filter import filter_by_language
from reward_hub.rule_engine import run_awards
from reward_hub.export import export_reward_workbook
from reward_hub.config_store import ConfigStore

ROOT = os.path.dirname(HERE)
FRONTEND = os.path.join(ROOT, "frontend")
PRESETS = os.path.join(common.app_data_dir(), "presets.json")
PORT = 8765


# ── Eastblue 下载任务（后台线程 + 进度轮询）─────────────────────────
JOBS = {}
JOBS_LOCK = threading.Lock()


def _run_eastblue(job_id, url):
    """后台线程：跑下载子进程，逐行收集进度，最后解析玩家表并存入 JOBS。"""
    script = os.path.join(HERE, "reward_hub", "eastblue_download.py")
    result, tail = None, []
    try:
        proc = subprocess.Popen(
            [sys.executable, script, "--url", url, "--outdir", common.work_dir()],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            s = line.strip()
            if not s:
                continue
            msg = None
            if s.startswith("{"):
                try:
                    msg = json.loads(s)
                except Exception:
                    msg = None
            if msg is None:
                tail.append(s); del tail[:-5]           # 保留末尾几行以便报错
                continue
            if "progress" in msg:
                with JOBS_LOCK:
                    JOBS[job_id]["progress"].append(msg["progress"])
            elif "ok" in msg:
                result = msg
        proc.wait()
    except Exception as e:
        result = {"ok": False, "error": str(e)}

    if result is None:
        result = {"ok": False, "error": (tail[-1] if tail else "下载进程无输出")}
    if result.get("ok"):
        try:
            from reward_hub.eastblue_parse import parse_players
            result["players"] = parse_players(result["path"])
        except Exception as e:
            result = {"ok": False, "error": "解析玩家表失败：%s" % e}
    with JOBS_LOCK:
        JOBS[job_id]["result"] = result
        JOBS[job_id]["done"] = True


def process_pipeline(raw_comments, players, dedup_strategy, target_langs, awards):
    """完整 Phase 1 流程：提取→去重→匹配→语言筛选→发奖。返回可预览的各 sheet。"""
    invalid = []
    rows = []
    for c in raw_comments:
        pid = extract_id(c.get("content", ""))
        if pid:
            rows.append({**c, "player_id": pid})
        else:
            invalid.append({**c, "reject_reason": "无有效ID"})

    rows = dedup(rows, dedup_strategy)

    matched = []
    for r in rows:
        info = players.get(r["player_id"])
        if info:
            matched.append({**r, **info})
        else:
            invalid.append({**r, "reject_reason": "Eastblue无记录"})

    passed, lang_rejected = filter_by_language(matched, set(target_langs))
    invalid.extend(lang_rejected)

    result, remaining = run_awards(passed, awards)
    return {"awards": result, "participation": remaining, "invalid": invalid}


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            with open(os.path.join(FRONTEND, "index.html"), "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/api/ping":
            self._json({"ok": True})
        elif self.path == "/api/presets":
            store = ConfigStore(PRESETS)
            self._json({"default": store.get_default(),
                        "presets": {n: store.load_preset(n) for n in store.list_presets()}})
        elif self.path.startswith("/api/eastblue/status"):
            job_id = (parse_qs(urlparse(self.path).query).get("job") or [""])[0]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if not job:
                    self._json({"ok": False, "error": "任务不存在"}, 404)
                    return
                self._json({"ok": True, "done": job["done"],
                            "progress": list(job["progress"]),
                            "result": job["result"]})
        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        try:
            if self.path == "/api/presets":
                b = self._body()
                store = ConfigStore(PRESETS)
                store.save_preset(b["name"], b["config"])
                if b.get("as_default"):
                    store.set_default(b["name"])
                self._json({"ok": True})
            elif self.path == "/api/process":
                b = self._body()
                out = process_pipeline(
                    b["raw_comments"], b.get("players", {}),
                    b.get("dedup_strategy", "earliest"),
                    b.get("target_langs", ["en"]), b.get("awards", []))
                self._json({"ok": True, **out})
            elif self.path == "/api/export":
                b = self._body()
                out_path = os.path.join(common.work_dir(), b.get("filename", "发奖名单.xlsx"))
                export_reward_workbook(out_path, b["awards"], b["participation"], b["invalid"])
                self._json({"ok": True, "path": out_path})
            elif self.path == "/api/eastblue":
                b = self._body()
                job_id = uuid.uuid4().hex
                with JOBS_LOCK:
                    JOBS[job_id] = {"progress": [], "done": False, "result": None}
                t = threading.Thread(target=_run_eastblue,
                                     args=(job_id, b["url"]), daemon=True)
                t.start()
                self._json({"ok": True, "job": job_id})
            else:
                self._json({"ok": False, "error": "not found"}, 404)
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)


if __name__ == "__main__":
    print("发奖中台已启动：http://127.0.0.1:%d" % PORT, flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
