# -*- coding: utf-8 -*-
"""用 Playwright 打开 Eastblue 下载链接，捕获自动下载的 xlsx。
用法: python3 eastblue_download.py --url "<下载链接>" --outdir <目录>
emit 一行 JSON: {ok, path} 或 {ok:false, error}
链接是网页地址(#/ 前端路由 + auto_download=1)，前端 JS 触发下载。
首次未登录会停在 SSO 页(headless=False)，人工登录后 profile 持久化免登。
"""
import os, sys, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
try:
    from reward_hub.common import emit, app_data_dir, work_dir
except ImportError:
    sys.path.insert(0, os.path.dirname(HERE))
    from reward_hub.common import emit, app_data_dir, work_dir


def download(url, outdir):
    from playwright.sync_api import sync_playwright
    profile = os.path.join(app_data_dir(), "eastblue_profile")
    os.makedirs(profile, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile, headless=False, accept_downloads=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            with page.expect_download(timeout=120000) as dl_info:
                page.goto(url)
                # 若停在登录页，人工登录后前端会自动重定向并触发下载
            dl = dl_info.value
            fname = dl.suggested_filename or "eastblue_players.xlsx"
            path = os.path.join(outdir, fname)
            dl.save_as(path)
            emit({"ok": True, "path": path})
        except Exception as e:
            emit({"ok": False, "error": str(e)})
        finally:
            ctx.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--outdir", default=work_dir())
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    download(a.url, a.outdir)
