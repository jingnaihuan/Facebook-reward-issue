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
    from reward_hub.common import emit, app_data_dir, work_dir
except ImportError:
    sys.path.insert(0, os.path.dirname(HERE))
    from reward_hub.common import emit, app_data_dir, work_dir


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


def _attempt(p, url, ids, outdir, headless, login_wait):
    profile = os.path.join(app_data_dir(), "eastblue_profile")
    os.makedirs(profile, exist_ok=True)
    ctx = p.chromium.launch_persistent_context(
        profile, headless=headless, accept_downloads=True)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url)
        # 等应用加载完成（登录成功后「+增加条件」才会出现）
        page.get_by_text("+增加条件", exact=False).first.wait_for(timeout=login_wait)
        page.wait_for_timeout(1500)
        return _search_and_export(page, ids, outdir)
    finally:
        ctx.close()


def download(url, ids, outdir):
    from playwright.sync_api import sync_playwright
    url = _strip_auto_download(url)
    with sync_playwright() as p:
        # 1) 无窗口优先（已登录情况下全程后台）
        _progress("启动无窗口浏览器…")
        try:
            _progress("打开玩家管理页面…")
            path = _attempt(p, url, ids, outdir, headless=True, login_wait=20000)
            _progress("导出完成，正在解析玩家表…")
            emit({"ok": True, "path": path})
            return
        except Exception:
            pass
        # 2) 回退：可见浏览器，等人工登录后再走一遍
        _progress("需要登录，已打开浏览器窗口，请完成 Eastblue 登录…", need_login=True)
        try:
            path = _attempt(p, url, ids, outdir, headless=False, login_wait=180000)
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--ids", default="")
    ap.add_argument("--ids-file", dest="ids_file", default="")
    ap.add_argument("--outdir", default=work_dir())
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    ids = _load_ids(a)
    if not ids:
        emit({"ok": False, "error": "没有可查询的玩家ID"})
        sys.exit(0)
    download(a.url, ids, a.outdir)
