# -*- coding: utf-8 -*-
"""用 Playwright 打开 Eastblue 下载链接，捕获自动下载的 xlsx。
用法: python3 eastblue_download.py --url "<下载链接>" --outdir <目录>
逐行 emit 进度 JSON: {"progress": "..."}，最后 emit 结果 {"ok":true,"path":...} 或 {"ok":false,"error":...}
链接是网页地址(#/ 前端路由 + auto_download=1)，前端 JS 触发下载。
默认无窗口(headless)运行；若因未登录/登录过期抓不到下载，自动回退为可见浏览器，
人工登录后 profile 持久化，后续即可全程无窗口。
"""
import os, sys, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
try:
    from reward_hub.common import emit, app_data_dir, work_dir
except ImportError:
    sys.path.insert(0, os.path.dirname(HERE))
    from reward_hub.common import emit, app_data_dir, work_dir


def _progress(msg, **extra):
    emit(dict({"progress": msg}, **extra))


def _attempt(p, url, outdir, headless, timeout):
    """单次尝试：打开链接并等待下载。成功返回文件路径，失败抛异常。"""
    profile = os.path.join(app_data_dir(), "eastblue_profile")
    os.makedirs(profile, exist_ok=True)
    ctx = p.chromium.launch_persistent_context(
        profile, headless=headless, accept_downloads=True)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        with page.expect_download(timeout=timeout) as dl_info:
            page.goto(url)
            # 若停在登录页，前端登录后会自动重定向并触发下载
        dl = dl_info.value
        fname = dl.suggested_filename or "eastblue_players.xlsx"
        path = os.path.join(outdir, fname)
        dl.save_as(path)
        return path
    finally:
        ctx.close()


def download(url, outdir):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        # 1) 先尝试无窗口（已登录情况下全程后台）
        _progress("启动无窗口浏览器…")
        try:
            _progress("打开 Eastblue 页面，正在下载…")
            path = _attempt(p, url, outdir, headless=True, timeout=25000)
            _progress("下载完成，正在解析玩家表…")
            emit({"ok": True, "path": path})
            return
        except Exception:
            pass
        # 2) 回退：可见浏览器，等待人工登录后自动下载
        _progress("需要登录，已打开浏览器窗口，请完成 Eastblue 登录…", need_login=True)
        try:
            path = _attempt(p, url, outdir, headless=False, timeout=180000)
            _progress("下载完成，正在解析玩家表…")
            emit({"ok": True, "path": path})
        except Exception as e:
            emit({"ok": False, "error": str(e)})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--outdir", default=work_dir())
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    download(a.url, a.outdir)
