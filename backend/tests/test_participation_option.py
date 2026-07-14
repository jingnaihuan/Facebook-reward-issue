# -*- coding: utf-8 -*-
"""第五页「被抽选中奖者是否可重复领参与奖」开关：
- 默认(关)：参与奖 = 未中奖者（历史行为不变）。
- 开：参与奖 = 全体有效参与者（含中奖者），顺序保持。
仅影响参与奖名单构成；抽选奖之间「一人最多中一档」不受影响。"""
import server


def _raw(order, pid):
    return {"order": order, "content": "帮我发奖 %s 谢谢" % pid,
            "likes": 0, "replies": 0, "time": ""}


def _players(*ids):
    return {pid: {"lang": "en", "role_name": "H"} for pid in ids}


def test_participation_excludes_winners_by_default():
    raw = [_raw(1, "1000000001"), _raw(2, "1000000002"), _raw(3, "1000000003")]
    players = _players("1000000001", "1000000002", "1000000003")
    awards = [{"name": "先锋奖", "rule": "top_floors", "n": 1}]
    out = server.process_pipeline(raw, players, "earliest", ["en"], awards)
    assert [w["player_id"] for w in out["awards"]["先锋奖"]] == ["1000000001"]
    assert [p["player_id"] for p in out["participation"]] == \
        ["1000000002", "1000000003"]


def test_participation_includes_winners_when_enabled():
    raw = [_raw(1, "1000000001"), _raw(2, "1000000002"), _raw(3, "1000000003")]
    players = _players("1000000001", "1000000002", "1000000003")
    awards = [{"name": "先锋奖", "rule": "top_floors", "n": 1}]
    out = server.process_pipeline(raw, players, "earliest", ["en"], awards,
                                  allow_winner_participation=True)
    assert [w["player_id"] for w in out["awards"]["先锋奖"]] == ["1000000001"]
    # 中奖者(1)同时留在参与奖名单，且全名单按 order 保持顺序
    assert [p["player_id"] for p in out["participation"]] == \
        ["1000000001", "1000000002", "1000000003"]


def test_award_winners_still_unique_across_awards_when_enabled():
    """开开关只影响参与奖；抽选奖之间仍不重复中奖。"""
    raw = [_raw(i, "100000000%d" % i) for i in range(1, 5)]
    players = _players(*["100000000%d" % i for i in range(1, 5)])
    awards = [{"name": "一等奖", "rule": "top_floors", "n": 2},
              {"name": "二等奖", "rule": "top_floors", "n": 2}]
    out = server.process_pipeline(raw, players, "earliest", ["en"], awards,
                                  allow_winner_participation=True)
    assert [w["player_id"] for w in out["awards"]["一等奖"]] == \
        ["1000000001", "1000000002"]
    assert [w["player_id"] for w in out["awards"]["二等奖"]] == \
        ["1000000003", "1000000004"]
    # 参与奖含全体（4人）
    assert len(out["participation"]) == 4
