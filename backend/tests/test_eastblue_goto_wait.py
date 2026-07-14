# -*- coding: utf-8 -*-
"""拉取环节的导航等待策略（不依赖 Playwright）。

回归背景：Eastblue 页面极重（数百个 JS 分包），办公网外（如 Mac 家用网络）
整页 load 事件常态 15~17s、偶发 >30s；扫码登录触发的跳转还会把同一次 goto 的
导航链拉长。Playwright 默认「30s 超时 + 等 load」会直接超时，误报
「登录未完成或超时」。故 goto 必须：只等 domcontentloaded + 放宽超时，
真正的就绪判定交给后续「+增加条件」元素等待。"""
from reward_hub import eastblue_download as ed


class _StopAfterGoto(Exception):
    """让流程在 goto 之后立即收尾，只考察 goto 的调用参数。"""


class _FakeLocator:
    def wait_for(self, timeout=None):
        raise _StopAfterGoto()


class _FakeMatch:
    first = _FakeLocator()


class _FakePage:
    def __init__(self, calls):
        self._calls = calls

    def goto(self, url, **kwargs):
        self._calls.append(kwargs)

    def get_by_text(self, *a, **k):
        return _FakeMatch()

    def wait_for_timeout(self, ms):
        pass


class _FakeCtx:
    def __init__(self, calls):
        self.pages = [_FakePage(calls)]

    def close(self):
        pass


def _goto_kwargs(monkeypatch, fn, *args):
    calls = []
    monkeypatch.setattr(ed, "_launch_persistent",
                        lambda p, profile, headless: _FakeCtx(calls))
    try:
        fn(*args)
    except _StopAfterGoto:
        pass
    assert len(calls) == 1, "应恰好发起一次 goto"
    return calls[0]


def test_attempt_goto_relaxed_wait(monkeypatch, tmp_path):
    # 就绪判定已抽到 _wait_ready_or_login；此处只考察 goto 参数，故把它 stub 成 goto 后即收尾
    monkeypatch.setattr(ed, "_wait_ready_or_login",
                        lambda page, timeout: (_ for _ in ()).throw(_StopAfterGoto()))
    kw = _goto_kwargs(monkeypatch, ed._attempt,
                      None, "http://x", ["1"], str(tmp_path), True, 9000)
    assert kw.get("wait_until") == "domcontentloaded"
    assert kw.get("timeout", 0) >= 60000


def test_login_only_goto_relaxed_wait(monkeypatch):
    kw = _goto_kwargs(monkeypatch, ed._login_only, None, "http://x", 180000)
    assert kw.get("wait_until") == "domcontentloaded"
    assert kw.get("timeout", 0) >= 60000
