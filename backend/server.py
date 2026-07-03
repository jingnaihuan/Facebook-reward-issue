# -*- coding: utf-8 -*-
"""发奖中台本地服务（标准库 http.server，无框架）。"""
import os, sys, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
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
            else:
                self._json({"ok": False, "error": "not found"}, 404)
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)


if __name__ == "__main__":
    print("发奖中台已启动：http://127.0.0.1:%d" % PORT, flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
