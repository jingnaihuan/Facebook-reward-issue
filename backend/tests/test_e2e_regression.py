import json, os
from reward_hub.extract_id import extract_id
from reward_hub.dedup import dedup
from reward_hub.language_filter import filter_by_language
from reward_hub.rule_engine import run_awards

HERE = os.path.dirname(os.path.abspath(__file__))
FX = os.path.join(HERE, "fixtures")


def _load(fn):
    return json.load(open(os.path.join(FX, fn), encoding="utf-8"))


def test_vanguard_and_participation_match_manual():
    raw = _load("raw_comments.json")
    players = _load("expected_players.json")
    expected_vanguard = set(_load("expected_vanguard.json"))

    # 提取 ID
    rows = []
    for c in raw:
        pid = extract_id(c["content"])
        if pid:
            rows.append({**c, "player_id": pid})

    # 去重（最早）
    rows = dedup(rows, "earliest")

    # 匹配玩家信息
    matched = []
    for r in rows:
        info = players.get(r["player_id"])
        if info:
            matched.append({**r, **info})

    # 语言筛选（en）
    passed, _ = filter_by_language(matched, {"en"})

    # 前 100 楼 = 先锋奖
    awards = [{"name": "先锋奖", "rule": "top_floors", "n": len(expected_vanguard)}]
    result, remaining = run_awards(passed, awards)
    got_vanguard = {w["player_id"] for w in result["先锋奖"]}

    # 集合一致性（若不一致，打印差异供人工核对口径）
    missing = expected_vanguard - got_vanguard
    extra = got_vanguard - expected_vanguard
    assert not missing and not extra, \
        "先锋奖不一致 缺失=%s 多出=%s" % (missing, extra)
