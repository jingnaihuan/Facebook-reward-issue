# -*- coding: utf-8 -*-
"""关键词匹配：解析关键词串 + 判定留言是否答对（剔除玩家ID后做包含匹配）。"""
from reward_hub.keyword import parse_keywords, is_answered


# ── parse_keywords ────────────────────────────────────────────────
def test_parse_single():
    assert parse_keywords("红色") == ["红色"]


def test_parse_comma_and_fullwidth_comma_and_dun():
    # 半角逗号 / 全角逗号 / 顿号都算分隔符
    assert parse_keywords("红色, red，红、RED") == ["红色", "red", "红", "red"]


def test_parse_newline():
    assert parse_keywords("红色\nred\n  蓝色  ") == ["红色", "red", "蓝色"]


def test_parse_lowercases():
    assert parse_keywords("RED, Blue") == ["red", "blue"]


def test_parse_drops_empty_items():
    assert parse_keywords(" , 红色, ,, ") == ["红色"]


def test_parse_empty_string():
    assert parse_keywords("") == []
    assert parse_keywords("   ") == []


def test_parse_keeps_internal_spaces():
    # 多词答案：只去首尾空格，保留词内空格
    assert parse_keywords("red car") == ["red car"]


# ── is_answered ───────────────────────────────────────────────────
def test_answered_simple_contains():
    assert is_answered("我猜是红色！", "1000000001", ["红色"]) is True


def test_not_answered_when_absent():
    assert is_answered("不知道啊", "1000000001", ["红色"]) is False


def test_answered_case_insensitive():
    assert is_answered("The answer is RED", "1000000001", ["red"]) is True


def test_answered_any_keyword_hits():
    # 多关键词 OR：命中任一即算对
    assert is_answered("我选 blue", "1000000001", ["红色", "red", "blue"]) is True


def test_id_digits_do_not_falsely_match():
    # 正答是 "12"，玩家ID 1200000012 含 12，但答案只在 ID 里 → 不算对
    assert is_answered("1200000012", "1200000012", ["12"]) is False


def test_answer_survives_after_id_stripped():
    # ID 剔除后，正文里独立出现的 "12" 仍算对
    assert is_answered("我猜12 1200000012", "1200000012", ["12"]) is True


def test_strips_all_id_occurrences():
    # ID 重复出现也要全部剔除，避免残留 ID 里的数字被当答案
    assert is_answered("1200000012 再报一次 1200000012", "1200000012", ["12"]) is False


def test_no_keywords_never_answered():
    assert is_answered("红色", "1000000001", []) is False


# ── 防御性边界 ─────────────────────────────────────────────────────
def test_parse_none_is_empty():
    assert parse_keywords(None) == []


def test_parse_carriage_return():
    assert parse_keywords("红色\r\n蓝色") == ["红色", "蓝色"]


def test_is_answered_handles_none_content():
    assert is_answered(None, "1000000001", ["红色"]) is False


def test_is_answered_none_player_id():
    # 没有ID可剔时，直接在正文里匹配
    assert is_answered("红色", None, ["红色"]) is True
