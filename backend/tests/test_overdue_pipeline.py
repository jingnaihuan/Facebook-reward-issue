# -*- coding: utf-8 -*-
"""第五步「留言时间筛选（逾期判定）」集成测试：逾期为最高优先级淘汰。"""
import server

WIN = {"mode": "before", "end": "2023-05-15T18:00"}   # 18:00 之后为逾期


def _raw(order, pid, t, content=None):
    return {"order": order, "content": content or ("帮我发奖 %s" % pid),
            "likes": 0, "replies": 0, "time": t}


def _players(*ids):
    return {pid: {"lang": "en", "role_name": "H"} for pid in ids}


def test_overdue_goes_invalid_and_not_in_awards():
    raw = [_raw(1, "1000000001", "2023-05-15T10:00:00+0000"),   # 界内
           _raw(2, "1000000002", "2023-05-15T20:00:00+0000")]   # 逾期
    players = _players("1000000001", "1000000002")
    awards = [{"name": "先锋奖", "rule": "top_floors", "n": 5}]
    out = server.process_pipeline(raw, players, "all", ["en"], awards, time_filter=WIN)
    won = [w["player_id"] for w in out["awards"]["先锋奖"]]
    assert "1000000002" not in won                       # 逾期者不进奖池
    assert won == ["1000000001"]
    reasons = {r["player_id"]: r["reject_reason"] for r in out["invalid"]}
    assert "1000000002" in reasons and reasons["1000000002"].startswith("逾期参与")
    assert out["overdue_stats"] == {"mode": "before", "overdue": 1, "no_time": 0}


def test_overdue_priority_over_no_id():
    # 既逾期又无有效ID → 原因必须是「逾期参与」，不是「无有效ID」
    raw = [_raw(1, None, "2023-05-15T20:00:00+0000", content="这条没有任何ID但很晚")]
    out = server.process_pipeline(raw, {}, "all", ["en"], [], time_filter=WIN)
    assert len(out["invalid"]) == 1
    assert out["invalid"][0]["reject_reason"].startswith("逾期参与")


def test_overdue_correct_answer_excluded_from_keyword_award():
    raw = [_raw(1, "1000000001", "2023-05-15T10:00:00+0000", content="1000000001 答案是 苹果"),
           _raw(2, "1000000002", "2023-05-15T20:00:00+0000", content="1000000002 答案是 苹果")]
    players = _players("1000000001", "1000000002")
    awards = [{"name": "答题奖", "rule": "answered_all", "keyword": "苹果"}]
    out = server.process_pipeline(raw, players, "all", ["en"], awards, time_filter=WIN)
    won = [w["player_id"] for w in out["awards"]["答题奖"]]
    assert won == ["1000000001"]                          # 逾期的正确答案不算


def test_no_time_row_participates_and_counted():
    raw = [_raw(1, "1000000001", ""),                      # 无时间戳 → 放行
           _raw(2, "1000000002", "2023-05-15T20:00:00+0000")]  # 逾期
    players = _players("1000000001", "1000000002")
    out = server.process_pipeline(raw, players, "all", ["en"], [], time_filter=WIN)
    part = [p["player_id"] for p in out["participation"]]
    assert "1000000001" in part                            # 无时间戳照常参与
    assert out["overdue_stats"]["no_time"] == 1
    assert out["overdue_stats"]["overdue"] == 1


def test_filter_off_matches_legacy_behavior():
    raw = [_raw(1, "1000000001", "2023-05-15T20:00:00+0000")]
    players = _players("1000000001")
    out = server.process_pipeline(raw, players, "all", ["en"], [])   # 不传 time_filter
    assert [p["player_id"] for p in out["participation"]] == ["1000000001"]
    assert out["overdue_stats"] == {"mode": "off", "overdue": 0, "no_time": 0}
