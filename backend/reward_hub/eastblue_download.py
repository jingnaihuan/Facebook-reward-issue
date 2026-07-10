# -*- coding: utf-8 -*-
"""用 Playwright 打开 Eastblue 玩家管理页，按「玩家ID」精确查询并导出 xlsx。
用法: python3 eastblue_download.py --url "<筛选链接>" --ids-file <每行一个ID> --outdir <目录>
     （或 --ids "id1,id2,..."）
逐行 emit 进度 JSON: {"progress": "..."}，最后 emit {"ok":true,"path":...} 或 {"ok":false,"error":...}

流程（对应人工操作）：加载带筛选参数的链接（页面预填语言/时间/排除内玩等）→
「+增加条件」→ 字段选「玩家ID」→ 操作符「在...之中」→ 值填入提取的玩家ID（每行一个）→
「搜索」→「导出」→ 捕获下载的 xlsx。

默认无窗口(headless)运行；若未登录/登录过期，自动弹出可见浏览器，人工登录后 profile 持久化。
"""
import os, sys, re, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
try:
    from reward_hub.common import emit, app_data_dir, work_dir, force_utf8_std
except ImportError:
    sys.path.insert(0, os.path.dirname(HERE))
    from reward_hub.common import emit, app_data_dir, work_dir, force_utf8_std


def _progress(msg, **extra):
    emit(dict({"progress": msg}, **extra))


def _strip_auto_download(url):
    """去掉 auto_download=1，避免页面在我们加 ID 条件前就自动下载。"""
    url = re.sub(r"[?&]auto_download=1", lambda m: "?" if m.group(0).startswith("?") else "", url)
    return url


def _search_and_export(page, ids, outdir):
    # 1) 增加条件
    _progress("添加「玩家ID」筛选条件…")
    page.get_by_text("+增加条件", exact=False).first.click()
    page.wait_for_timeout(800)
    # 2) 字段：默认「负责人」→ 打开列表选「玩家ID」
    page.get_by_text("负责人", exact=False).first.click()
    page.wait_for_timeout(600)
    page.locator(".itemDiv", has_text="玩家ID").first.click()
    page.wait_for_timeout(600)
    # 3) 值：点「不限」展开文本框，每行一个填入 ID（操作符「在...之中」保持默认）
    page.get_by_text("不限", exact=False).last.click()
    page.wait_for_timeout(500)
    page.locator("textarea.ep-textarea__inner:visible").first.fill("\n".join(ids))
    page.wait_for_timeout(300)
    page.keyboard.press("Escape")          # 关掉值弹层（值已通过 input 提交）
    page.wait_for_timeout(400)
    # 4) 搜索：必须等搜索接口返回才算结果就绪（结果多时可能耗时几十秒），
    #    不能只靠固定等待，否则会在结果没出来时就点导出、导出空表/旧数据。
    _progress("正在按 %d 个玩家ID 搜索（结果多时请稍候）…" % len(ids))
    is_search = lambda r: ("player-management" in r.url and "/search" in r.url
                           and r.request.method == "POST")
    with page.expect_response(is_search, timeout=180000) as resp_info:
        page.get_by_role("button", name="搜索", exact=True).first.click()
    if resp_info.value.status >= 400:
        raise RuntimeError("搜索接口返回 HTTP %s" % resp_info.value.status)
    page.wait_for_timeout(1500)          # 结果渲染缓冲，确保导出取到完整结果
    # 5) 导出（部分导出会弹确认框；大结果集生成 xlsx 也可能较慢）
    _progress("搜索完成，正在导出…")
    with page.expect_download(timeout=180000) as dl_info:
        page.get_by_role("button", name="导出", exact=True).first.click()
        try:
            page.get_by_role("button", name=re.compile("确定|确认|导出")).last.click(timeout=4000)
        except Exception:
            pass
    dl = dl_info.value
    fname = dl.suggested_filename or "eastblue_players.xlsx"
    path = os.path.join(outdir, fname)
    dl.save_as(path)
    return path


def _browser_channel():
    """驱动系统已装浏览器：Windows 用自带 Edge，Mac 用 Chrome（均为 Chromium 内核）。
    这样不依赖需联网下载的内置 chromium，避免公司网络挡住 CDN 下载。"""
    return "msedge" if sys.platform.startswith("win") else "chrome"


def _launch_persistent(p, profile, headless):
    """优先用系统 Chrome/Edge 启动持久化上下文；系统浏览器缺失时回退到内置 chromium。"""
    kwargs = dict(headless=headless, accept_downloads=True)
    try:
        return p.chromium.launch_persistent_context(profile, channel=_browser_channel(), **kwargs)
    except Exception as e:
        low = str(e).lower()
        miss = ("executable doesn't exist" in low or "could not find" in low
                or ("channel" in low and "not found" in low))
        if not miss:
            raise                       # profile 占用/网络等其它错误，照常抛出
        return p.chromium.launch_persistent_context(profile, **kwargs)  # 回退内置内核


# 检测/等待时长（毫秒），集中在此便于调整：
HEADLESS_DETECT_WAIT = 9000    # 无窗口下判定「已登录 or 需登录」的最长等待（缩短自 20s）
VISIBLE_LOGIN_WAIT = 180000    # 可见窗口里等用户完成 SSO 登录的最长时间
RELOGIN_DETECT_WAIT = 30000    # 登录后无窗口重跑时，等页面就绪的最长时间（登录态已在，通常很快）
PAGE_GOTO_TIMEOUT = 120000     # goto 只等 domcontentloaded、不等整页 load：页面极重（数百 JS 分包），
                               # 办公网外 load 常态 15s+，扫码跳转还会拉长导航链，默认 30s+load 必误报；
                               # 真正的就绪判定交给下方「+增加条件」元素等待，此超时仅兜底断网类故障

_LOGIN_MARK = "+增加条件"       # 该按钮出现 = 已登录且页面就绪


def _is_no_browser(err):
    low = str(err).lower()
    return "executable doesn't exist" in low or "could not find" in low


def _emit_no_browser():
    emit({"ok": False, "error":
          "未检测到可用浏览器（需要 Google Chrome 或 Microsoft Edge）。"
          "Windows 一般自带 Edge；若确实没有，请安装 Chrome 后重试。"})


def _attempt(p, url, ids, outdir, headless, login_wait):
    profile = os.path.join(app_data_dir(), "eastblue_profile")
    os.makedirs(profile, exist_ok=True)
    ctx = _launch_persistent(p, profile, headless)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=PAGE_GOTO_TIMEOUT)
        # 等应用加载完成（登录成功后「+增加条件」才会出现；元素一出现即返回，不会白等满 login_wait）
        page.get_by_text(_LOGIN_MARK, exact=False).first.wait_for(timeout=login_wait)
        page.wait_for_timeout(1500)
        return _search_and_export(page, ids, outdir)
    finally:
        ctx.close()


def _login_only(p, url, login_wait):
    """可见窗口仅用于登录：等『+增加条件』出现（=登录完成、页面就绪）后立即关窗。
    登录态已持久化到 profile，真正的搜索/导出改由无窗口浏览器完成，避免留窗口让用户误操作。"""
    profile = os.path.join(app_data_dir(), "eastblue_profile")
    os.makedirs(profile, exist_ok=True)
    ctx = _launch_persistent(p, profile, headless=False)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=PAGE_GOTO_TIMEOUT)
        page.get_by_text(_LOGIN_MARK, exact=False).first.wait_for(timeout=login_wait)
        page.wait_for_timeout(600)
    finally:
        ctx.close()      # 无论登录成功与否都关窗，不残留窗口


def download(url, ids, outdir):
    from playwright.sync_api import sync_playwright
    url = _strip_auto_download(url)
    with sync_playwright() as p:
        # 1) 无窗口优先：已登录则全程后台完成（判定超时已缩短）
        _progress("启动无窗口浏览器…")
        try:
            _progress("打开玩家管理页面…")
            path = _attempt(p, url, ids, outdir, headless=True, login_wait=HEADLESS_DETECT_WAIT)
            _progress("导出完成，正在解析玩家表…")
            emit({"ok": True, "path": path})
            return
        except Exception as e:
            if _is_no_browser(e):
                _emit_no_browser(); return
            # 其它异常（多为未登录导致等不到「+增加条件」）→ 转登录流程

        # 2) 可见窗口仅登录：登录成功即关窗
        _progress("需要登录，已打开浏览器窗口，请完成 Eastblue 登录（登录后窗口会自动关闭）…", need_login=True)
        try:
            _login_only(p, url, login_wait=VISIBLE_LOGIN_WAIT)
        except Exception as e:
            if _is_no_browser(e):
                _emit_no_browser(); return
            emit({"ok": False, "error": "登录未完成或超时：%s" % e}); return

        # 3) 登录态已持久化 → 无窗口重跑正事（搜索/导出全程后台）
        _progress("登录成功，登录窗口已关闭，正在后台拉取…")
        try:
            path = _attempt(p, url, ids, outdir, headless=True, login_wait=RELOGIN_DETECT_WAIT)
            _progress("导出完成，正在解析玩家表…")
            emit({"ok": True, "path": path})
        except Exception as e:
            emit({"ok": False, "error": str(e)})


def _load_ids(a):
    if a.ids_file:
        with open(a.ids_file, encoding="utf-8") as f:
            raw = f.read()
    else:
        raw = a.ids or ""
    ids, seen = [], set()
    for tok in re.split(r"[\s,]+", raw):
        tok = tok.strip()
        if tok and tok not in seen:
            seen.add(tok); ids.append(tok)
    return ids


def main(argv=None):
    """脚本入口。开发模式由 `python3 eastblue_download.py ...` 调用；
    冻结模式由 app_entry 的 `--run-script eastblue ...` 分发到此（argv 为剩余参数列表）。"""
    force_utf8_std()          # 冻结版 console=False 时 stdout 可能为 None / 非 UTF-8，先修好
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--ids", default="")
    ap.add_argument("--ids-file", dest="ids_file", default="")
    ap.add_argument("--outdir", default=work_dir())
    a = ap.parse_args(argv)
    os.makedirs(a.outdir, exist_ok=True)
    ids = _load_ids(a)
    if not ids:
        emit({"ok": False, "error": "没有可查询的玩家ID"})
        return 0
    download(a.url, ids, a.outdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
