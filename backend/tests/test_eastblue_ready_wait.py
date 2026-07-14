# -*- coding: utf-8 -*-
"""拉取环节「就绪 vs 需登录」判定（不依赖 Playwright）。

回归背景：Eastblue 玩家管理页极重，慢网络下渲染出「+增加条件」可能要 30s~180s。
原逻辑无窗口首探只等 9s、登录后重跑只等 30s，慢机器上：
  - 首探必超时 → 每次都白弹登录窗；
  - 重跑 30s 也可能没渲染完 → 报「拉取失败：Timeout 30000ms」。
改法：改成「等到就绪 或 已跳去登录页」的判定 + 放宽超时上限。
判定「需登录」用 URL 是否离开玩家管理页（不依赖登录页具体元素）——即使判错，
也只是退回到弹登录窗的老行为，不会误发/漏发，属安全兜底。"""
from reward_hub import eastblue_download as ed


class _FakeLocator:
    def __init__(self, visible):
        self._visible = visible

    def is_visible(self):
        return self._visible


class _FakeMatch:
    def __init__(self, visible):
        self.first = _FakeLocator(visible)


class _FakePage:
    def __init__(self, url, marker_visible):
        self.url = url
        self._marker_visible = marker_visible

    def get_by_text(self, *a, **k):
        return _FakeMatch(self._marker_visible)

    def wait_for_timeout(self, ms):
        pass


def test_looks_like_login_false_on_player_page():
    page = _FakePage("https://eastblue.example/player-management/list", False)
    assert ed._looks_like_login(page) is False


def test_looks_like_login_true_when_redirected_away():
    page = _FakePage("https://sso.example.com/login?redirect=x", False)
    assert ed._looks_like_login(page) is True


def test_wait_ready_true_when_marker_visible():
    page = _FakePage("https://eastblue.example/player-management", True)
    assert ed._wait_ready_or_login(page, 5000) is True


def test_wait_ready_false_when_redirected_to_login():
    # 已跳去登录页且没出现就绪标记 → 立即判需登录（不空等满超时）
    page = _FakePage("https://sso.example.com/login", False)
    assert ed._wait_ready_or_login(page, 60000) is False


def test_wait_ready_false_after_timeout_if_never_ready():
    # 仍停在玩家管理页但迟迟不就绪 → 到超时兜底判需登录
    page = _FakePage("https://eastblue.example/player-management", False)
    assert ed._wait_ready_or_login(page, 50) is False


def test_relogin_detect_wait_is_generous():
    """登录后重跑的等待必须足够长，覆盖极慢页面（原 30s 会误报拉取失败）。"""
    assert ed.RELOGIN_DETECT_WAIT >= 90000


def test_headless_detect_wait_is_generous():
    """首探等待也要够长，否则慢机器上「已登录但慢」会被误判为需登录、每次白弹窗。"""
    assert ed.HEADLESS_DETECT_WAIT >= 45000
