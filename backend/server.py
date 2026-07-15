# -*- coding: utf-8 -*-
"""发奖中台本地服务（标准库 http.server，无框架）。"""
import os, sys, json, time, uuid, threading, subprocess, tempfile, datetime, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from reward_hub import common
from reward_hub import platform_util
from reward_hub.extract_id import extract_id
from reward_hub.dedup import dedup
from reward_hub.language_filter import filter_by_language
from reward_hub.rule_engine import run_awards
from reward_hub.export import export_reward_workbook
from reward_hub.config_store import ConfigStore

# 前端资源目录：冻结后从 PyInstaller 解包目录(_MEIPASS)读，开发模式从仓库 frontend/ 读。
if common.is_frozen():
    FRONTEND = os.path.join(getattr(sys, "_MEIPASS", HERE), "frontend")
else:
    ROOT = os.path.dirname(HERE)
    FRONTEND = os.path.join(ROOT, "frontend")
PRESETS = os.path.join(common.app_data_dir(), "presets.json")
PORT = 18765


def _eastblue_cmd(url, ids_path, outdir):
    """构造 Eastblue 下载子进程命令：
    开发模式 `python3 eastblue_download.py --url ...`；
    冻结模式 `<exe> --run-script eastblue --url ...`（由 app_entry 分发到 eastblue_download.main）。
    冻结版里 sys.executable 是打包 exe 本身，无法直接跑 .py，必须走自我重入分发。"""
    args = ["--url", url, "--ids-file", ids_path, "--outdir", outdir]
    if common.is_frozen():
        return [sys.executable, "--run-script", "eastblue"] + args
    script = os.path.join(HERE, "reward_hub", "eastblue_download.py")
    return [sys.executable, script] + args


# ── Eastblue 下载任务（后台线程 + 进度轮询）─────────────────────────
JOBS = {}
JOBS_LOCK = threading.Lock()


def _run_eastblue(job_id, url, ids):
    """后台线程：按玩家ID跑下载子进程，逐行收集进度，最后解析玩家表并存入 JOBS。"""
    result, tail = None, []
    ids_path = os.path.join(tempfile.gettempdir(), "reward_hub_ids_%s.txt" % job_id)
    try:
        with open(ids_path, "w", encoding="utf-8") as f:
            f.write("\n".join(str(i) for i in ids))
        # 不新建进程组：让子进程与浏览器留在同一控制台/会话，关闭终端或命令行窗口时
        # 系统会把关闭信号级联到整棵进程树，自动终止，不残留后台进程。
        proc = subprocess.Popen(
            _eastblue_cmd(url, ids_path, common.work_dir()),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            # 子进程 emit 的是 UTF-8（含中文进度）。必须显式指定编码，
            # 否则中文版 Windows 会用 cp936 解码导致乱码 / JSON 解析失败。
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            # 打包版(无黑框)在 Windows 上拉子进程会闪控制台窗，抑制之。
            **common.no_window_kwargs())
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["proc"] = proc      # 记录以便退出时清理
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
    finally:
        try:
            os.remove(ids_path)
        except OSError:
            pass

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


def process_pipeline(raw_comments, players, dedup_strategy, target_langs, awards,
                     allow_winner_participation=False):
    """完整 Phase 1 流程：提取→去重→匹配→语言筛选→发奖。返回可预览的各 sheet。
    allow_winner_participation：抽选中奖者是否也进参与奖名单。
      False(默认)=参与奖仅未中奖者（历史行为）；True=参与奖 = 全体有效参与者（含中奖者）。
      仅影响参与奖名单构成，不改变抽选奖之间「一人最多中一档」。"""
    invalid = []
    valid = []                          # 提取到ID的全部留言（未去重，一人可多条）
    for c in raw_comments:
        content = c.get("content", "")
        pid = extract_id(content)
        if pid:
            valid.append({**c, "player_id": pid})
        elif not str(content).strip():
            # 纯图片/动图/贴图等无文字留言：计入无效并标清原因，不再是空白行
            invalid.append({**c, "reject_reason": "空内容（图片/动图等，无文字）"})
        else:
            invalid.append({**c, "reject_reason": "无有效ID"})

    # 主路径：去重→匹配→语言筛（无效名单按去重后口径统计，与既有行为一致）。
    deduped = dedup(valid, dedup_strategy)
    matched = []
    for r in deduped:
        info = players.get(r["player_id"])
        if info:
            matched.append({**r, **info})
        else:
            invalid.append({**r, "reject_reason": "Eastblue无记录"})

    passed, lang_rejected = filter_by_language(matched, set(target_langs))
    invalid.extend(lang_rejected)

    # 关键词奖要在『玩家全部留言』上判答对（去重可能恰好留下答错那条），
    # 故用未去重的 valid 另建一份「匹配+语言筛」的全量池；无关键词奖时不构建，零开销。
    all_comments = None
    if any((a.get("keyword") or "").strip() or a.get("rule") == "answered_all"
           for a in awards):
        all_matched = [{**r, **players[r["player_id"]]}
                       for r in valid if players.get(r["player_id"])]
        all_comments, _ = filter_by_language(all_matched, set(target_langs))

    result, remaining = run_awards(passed, awards, all_comments=all_comments)
    # 开关开：参与奖 = 全体有效参与者（含中奖者）；关：仅未中奖者。
    # 普惠奖(awards 为空)时 passed == remaining，开关无实际差异。
    participation = passed if allow_winner_participation else remaining
    return {"awards": result, "participation": participation, "invalid": invalid}


def write_run_log(inputs, out):
    """每次结算落一份运行日志（时间/规则/种子/各名单）到工作区「结算日志」目录，
    供事后查证「某次发奖到底选了谁」。任何异常都不得影响发奖本身，故整体兜底。
    返回写入路径，失败返回 None。"""
    try:
        awards_cfg = inputs.get("awards") or []
        universal = not awards_cfg          # 空奖项 = 普惠奖（全员）
        if universal:
            part_label = "普惠奖（全员）"
        elif inputs.get("allow_winner_participation"):
            part_label = "参与奖（含中奖者）"
        else:
            part_label = "参与奖（未中奖）"
        now = datetime.datetime.now()
        rec = {
            "时间": now.strftime("%Y-%m-%d %H:%M:%S"),
            "模式": "普惠奖（全员）" if universal else "抽选",
            "去重策略": inputs.get("dedup_strategy", "earliest"),
            "目标语言": inputs.get("target_langs", []),
            "奖项配置": awards_cfg,          # 每项含 name / rule / n / seed（随机时）
            "各奖项中奖": {name: [w.get("player_id") for w in winners]
                          for name, winners in out["awards"].items()},
            part_label: [p.get("player_id") for p in out["participation"]],
            "无效": [{"player_id": r.get("player_id", ""), "原因": r.get("reject_reason", "")}
                    for r in out["invalid"]],
        }
        logdir = os.path.join(common.work_dir(), "结算日志")
        os.makedirs(logdir, exist_ok=True)
        path = os.path.join(logdir, "结算-%s.json" % now.strftime("%Y%m%d-%H%M%S"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        return path
    except Exception:
        return None


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
        elif self.path in ("/api/ping", "/api/keepalive"):
            _touch_alive()          # 前端每 4s 心跳；看门狗据此判断网页是否还开着
            self._json({"ok": True})
        elif self.path == "/api/shutdown":
            # 主动退出（app_entry 启动新实例前先请旧实例自愿退出）。先回包再退，避免连接被重置。
            self._json({"ok": True})
            threading.Timer(0.3, lambda: os._exit(0)).start()
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
                    b.get("target_langs", ["en"]), b.get("awards", []),
                    allow_winner_participation=bool(b.get("allow_winner_participation")))
                log_path = write_run_log(b, out)      # 落审计日志，不影响返回
                self._json({"ok": True, "log_path": log_path, **out})
            elif self.path == "/api/export":
                b = self._body()
                default_name = "发奖名单-%s.xlsx" % datetime.datetime.now().strftime("%Y%m%d")
                kind, out_path = platform_util.choose_save_path(default_name)
                if kind == "cancel":
                    self._json({"ok": False, "cancelled": True, "error": "已取消导出"})
                    return
                if kind == "fallback":          # 非 Mac / 无原生对话框：落到默认工作区
                    out_path = os.path.join(common.work_dir(), default_name)
                export_reward_workbook(out_path, b["awards"], b["participation"], b["invalid"],
                                       allow_winner_participation=bool(b.get("allow_winner_participation")),
                                       keyword_award_names=b.get("keyword_award_names") or [])
                self._json({"ok": True, "path": out_path})
            elif self.path == "/api/eastblue":
                b = self._body()
                ids = b.get("ids") or []
                if not ids:
                    self._json({"ok": False, "error": "没有可查询的玩家ID"}, 400)
                    return
                job_id = uuid.uuid4().hex
                with JOBS_LOCK:
                    JOBS[job_id] = {"progress": [], "done": False, "result": None, "proc": None}
                t = threading.Thread(target=_run_eastblue,
                                     args=(job_id, b["url"], ids), daemon=True)
                t.start()
                self._json({"ok": True, "job": job_id})
            else:
                self._json({"ok": False, "error": "not found"}, 404)
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)


def _open_browser():
    """服务就绪后打开浏览器。两端统一交给 Python，启动脚本不再各自 open/start。
    用 localhost（而非 127.0.0.1），FB 方式 A 登录才不会被拦。
    设环境变量 REWARD_HUB_NO_BROWSER=1 可关闭（测试 / 由预览器托管时）。"""
    if os.environ.get("REWARD_HUB_NO_BROWSER") == "1":
        return
    try:
        webbrowser.open("http://localhost:%d" % PORT)
    except Exception:
        pass


def _terminate_proc_tree(proc):
    """终止下载子进程及其浏览器（安全网：用于 kill <服务pid> 这类不会级联到子进程的情况；
    关闭终端/命令行窗口的常见情况由系统级联终止，无需这里介入）。不会误杀服务自身。"""
    try:
        if proc is None or proc.poll() is not None:
            return
        if os.name == "nt":
            # /T 连同子进程树（含浏览器）一起结束，仅针对该子进程 PID，不影响服务自身
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True)
        else:
            # 只终止该子进程（Playwright 浏览器在其父进程退出后会自行关闭）
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
    except Exception:
        pass


def _cleanup_jobs():
    """服务退出时杀掉所有仍在跑的 Eastblue 下载子进程及其浏览器。"""
    with JOBS_LOCK:
        procs = [j.get("proc") for j in JOBS.values()]
    for proc in procs:
        _terminate_proc_tree(proc)


# ── 进程看门狗 ─────────────────────────────────────────────────────
# 打包版(.app/.exe)没有终端窗口，无法靠"关终端"停服务。改由前端心跳驱动：
# 前端每 4s ping 一次 /api/ping，超过宽限期无心跳（= 网页已关 / 电脑休眠）则自动退出，
# 实现「关网页后台自动关」，并避免迭代后旧后台残留。
# 宽限取 5 分钟：浏览器对切到后台的标签会把定时器降频到最狠约 1/分钟，300s 有 5 倍余量，
# 填表途中切走别的窗口也不会被误杀（代价仅是真关网页后进程多赖几分钟才退，无害）。
WATCHDOG_GRACE = 300       # 秒。
_last_alive = [time.time()]


def _touch_alive():
    _last_alive[0] = time.time()


def _any_job_active():
    """是否有 Eastblue 下载任务仍在跑（未完成）。子进程自带超时上限，不会长期赖住。"""
    with JOBS_LOCK:
        return any(not j.get("done") for j in JOBS.values())


def _watchdog_expired(now):
    """看门狗判定谓词（抽出便于单测）：距上次心跳是否已超过宽限期。
    ★ 有下载任务在跑时永不判过期——否则后台标签被降频、心跳拖过宽限，
       会把服务连同正在跑的 Eastblue 下载子进程一起误杀。"""
    if _any_job_active():
        return False
    return (now - _last_alive[0]) > WATCHDOG_GRACE


def _watchdog():
    while True:
        time.sleep(5)
        if _watchdog_expired(time.time()):
            _cleanup_jobs()
            os._exit(0)


def main():
    """服务入口。开发模式 `python3 server.py` 直接调用；
    冻结模式由 packaging/app_entry 在后台线程调用（信号注册在子线程会被下方 try 吞掉，无害）。"""
    import atexit, signal
    atexit.register(_cleanup_jobs)

    def _on_signal(signum, frame):
        _cleanup_jobs()
        os._exit(0)

    # Ctrl+C / kill / 关闭终端(SIGHUP) 时都先清理子进程再退出（信号只能在主线程注册，
    # 冻结版里 main 跑在子线程，signal.signal 会抛 ValueError，被 except 吞掉——由看门狗兜底）。
    _sigs = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        _sigs.append(signal.SIGHUP)
    for _s in _sigs:
        try:
            signal.signal(_s, _on_signal)
        except (ValueError, OSError):
            pass

    common.write_pid_file()                 # 供下次启动兜底定位旧实例
    _touch_alive()
    threading.Thread(target=_watchdog, daemon=True).start()

    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)  # 此时已 bind+listen
    print("发奖中台已启动：http://localhost:%d" % PORT, flush=True)
    threading.Timer(0.6, _open_browser).start()
    try:
        httpd.serve_forever()
    finally:
        _cleanup_jobs()


if __name__ == "__main__":
    main()
