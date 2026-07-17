# -*- coding: utf-8 -*-
"""回归：按玩家ID拉取时须把「玩家语言」放开为全部，否则页面默认只按登录语言(en)筛，
会把非该语言玩家漏成「无记录」。此处覆盖搜索请求体的语言数校验(防静默只拉单一语言)。
不依赖 Playwright —— 只测纯函数 _lang_count_in_search。"""
import json
from reward_hub.eastblue_download import _lang_count_in_search


def test_multi_language_passes_guard():
    body = json.dumps({"filters": {"game_langs": ["en", "fr", "de", "es"]}})
    assert _lang_count_in_search(body) == 4     # >=2 → 放开成功，不中止


def test_single_language_triggers_guard():
    # 只放开到单一语言 = 「全选」未生效，应低于阈值以触发中止（正是本次 bug 的表现）
    body = json.dumps({"filters": {"game_langs": ["en"]}})
    assert _lang_count_in_search(body) < 2


def test_missing_or_malformed_counts_zero():
    assert _lang_count_in_search("") == 0
    assert _lang_count_in_search(None) == 0
    assert _lang_count_in_search("not-json") == 0
    assert _lang_count_in_search(json.dumps({"filters": {}})) == 0
    assert _lang_count_in_search(json.dumps({})) == 0
