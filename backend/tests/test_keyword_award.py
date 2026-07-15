# -*- coding: utf-8 -*-
"""关键词抽奖端到端（server.process_pipeline）。

重点覆盖『代表留言口径 ≠ 全局去重』这一冲突：玩家先答错后答对、多次答对、
去重策略(earliest/best_likes)不同都不能让关键词奖漏判或用错那条留言。
"""
import server


def _raw(order, content, likes=0, replies=0):
    return {"order": order, "content": content, "likes": likes,
            "replies": replies, "time": "2026-06-26 08:%02d:00" % order}


def _players(*ids):
    return {pid: {"lang": "en", "role_name": "H"} for pid in ids}


P1, P2, P3 = "1000000001", "1000000002", "1000000003"


def test_wrong_then_right_caught_across_dedup():
    """先答错(1楼)后答对(5楼)：去重(最早)会留下错误那条，关键词奖仍要判其答对，
    且代表留言取『答对那条』(5楼)。"""
    raw = [
        _raw(1, "不知道 " + P1),      # P1 先答错
        _raw(2, "红色 " + P2),        # P2 直接答对
        _raw(5, "红色 " + P1),        # P1 后答对
    ]
    awards = [{"name": "答题奖", "rule": "top_floors", "n": 2, "keyword": "红色"}]
    out = server.process_pipeline(raw, _players(P1, P2), "earliest", ["en"], awards)
    winners = out["awards"]["答题奖"]
    assert [w["player_id"] for w in winners] == [P2, P1]     # 按答对楼层排序
    p1_win = next(w for w in winners if w["player_id"] == P1)
    assert p1_win["order"] == 5                              # 用的是答对那条的楼层


def test_wrong_answerer_still_gets_participation():
    """答错的人不进关键词奖，但仍是有效参与者，照常进参与奖。"""
    raw = [_raw(1, "红色 " + P1), _raw(2, "乱答 " + P2)]
    awards = [{"name": "答题奖", "rule": "top_floors", "n": 5, "keyword": "红色"}]
    out = server.process_pipeline(raw, _players(P1, P2), "earliest", ["en"], awards)
    assert [w["player_id"] for w in out["awards"]["答题奖"]] == [P1]
    assert [p["player_id"] for p in out["participation"]] == [P2]   # 答错者留在参与奖


def test_id_digits_not_false_positive_e2e():
    """正答是数字 12：玩家ID含12不算答对，正文里独立出现12才算。"""
    raw = [
        _raw(1, "1200000012"),                 # 只报了ID(恰含12)，没作答
        _raw(2, "我猜 12 号 " + P2),            # 正文含 12
    ]
    awards = [{"name": "答题奖", "rule": "top_floors", "n": 5, "keyword": "12"}]
    out = server.process_pipeline(raw, _players("1200000012", P2), "earliest", ["en"], awards)
    assert [w["player_id"] for w in out["awards"]["答题奖"]] == [P2]


def test_best_likes_dedup_does_not_hide_correct_answer():
    """去重=点赞最高时留下的可能是高赞错答；关键词奖仍靠全量留言判答对。"""
    raw = [
        _raw(1, "红色 " + P1, likes=1),         # 正确但低赞
        _raw(2, "哈哈 " + P1, likes=99),        # 错误但高赞（去重 best_likes 会留这条）
        _raw(3, "红色 " + P2, likes=5),
    ]
    awards = [{"name": "答题奖", "rule": "top_floors", "n": 5, "keyword": "红色"}]
    out = server.process_pipeline(raw, _players(P1, P2), "best_likes", ["en"], awards)
    assert {w["player_id"] for w in out["awards"]["答题奖"]} == {P1, P2}


def test_keyword_top_likes_uses_best_liked_correct_e2e():
    """点赞奖+答对：多次答对取点赞最高那条。"""
    raw = [
        _raw(1, "红色 " + P1, likes=2),
        _raw(4, "红色 " + P1, likes=80),        # 同一人更高赞的答对
        _raw(2, "红色 " + P2, likes=30),
    ]
    awards = [{"name": "答题点赞奖", "rule": "top_likes", "n": 1, "keyword": "红色"}]
    out = server.process_pipeline(raw, _players(P1, P2), "all", ["en"], awards)
    winners = out["awards"]["答题点赞奖"]
    assert [w["player_id"] for w in winners] == [P1]
    assert winners[0]["likes"] == 80


def test_keyword_and_normal_award_coexist():
    """特殊奖(关键词，排前) + 普通盖楼奖(排后)：一人一档跨两类生效。"""
    raw = [
        _raw(1, "红色 " + P1),
        _raw(2, "红色 " + P2),
        _raw(3, "乱答 " + P3),
    ]
    awards = [
        {"name": "答题奖", "rule": "top_floors", "n": 1, "keyword": "红色"},  # → P1
        {"name": "盖楼奖", "rule": "top_floors", "n": 2},                      # → P2, P3
    ]
    out = server.process_pipeline(raw, _players(P1, P2, P3), "earliest", ["en"], awards)
    assert [w["player_id"] for w in out["awards"]["答题奖"]] == [P1]
    assert [w["player_id"] for w in out["awards"]["盖楼奖"]] == [P2, P3]


def test_answered_all_e2e():
    """全部命中(答对即得)：所有答对的人都发。"""
    raw = [_raw(1, "红色 " + P1), _raw(2, "错 " + P2), _raw(3, "红色 " + P3)]
    awards = [{"name": "全对奖", "rule": "answered_all", "keyword": "红色"}]
    out = server.process_pipeline(raw, _players(P1, P2, P3), "earliest", ["en"], awards)
    assert [w["player_id"] for w in out["awards"]["全对奖"]] == [P1, P3]


def test_winner_row_carries_content_for_export():
    """关键词奖中奖行要带上『命中的留言内容』，供导出/预览人工复核。"""
    raw = [_raw(1, "我猜红色 " + P1)]
    awards = [{"name": "答题奖", "rule": "top_floors", "n": 1, "keyword": "红色"}]
    out = server.process_pipeline(raw, _players(P1), "earliest", ["en"], awards)
    assert out["awards"]["答题奖"][0]["content"] == "我猜红色 " + P1


def test_language_filter_still_applies_to_keyword_pool():
    """关键词奖候选也要过语言筛：答对但语言不符的不算。"""
    raw = [_raw(1, "红色 " + P1), _raw(2, "红色 " + P2)]
    players = {P1: {"lang": "en", "role_name": "H"},
               P2: {"lang": "de", "role_name": "H"}}
    awards = [{"name": "答题奖", "rule": "top_floors", "n": 5, "keyword": "红色"}]
    out = server.process_pipeline(raw, players, "earliest", ["en"], awards)
    assert [w["player_id"] for w in out["awards"]["答题奖"]] == [P1]   # P2 语言不符被排除


def test_unmatched_player_not_in_keyword_pool():
    """答对但 Eastblue 无记录的玩家不算（与普通奖同一道门槛）。"""
    raw = [_raw(1, "红色 " + P1), _raw(2, "红色 " + P2)]
    out = server.process_pipeline(raw, _players(P1), "earliest", ["en"],
                                  [{"name": "答题奖", "rule": "top_floors", "n": 5, "keyword": "红色"}])
    assert [w["player_id"] for w in out["awards"]["答题奖"]] == [P1]   # P2 无记录


def test_normal_award_unaffected_when_no_keyword():
    """无任何关键词奖时，行为与既有完全一致（回归保护）。"""
    raw = [_raw(i, "帮我发奖 100000000%d" % i) for i in range(1, 4)]
    players = _players(*["100000000%d" % i for i in range(1, 4)])
    awards = [{"name": "盖楼奖", "rule": "top_floors", "n": 1}]
    out = server.process_pipeline(raw, players, "earliest", ["en"], awards)
    assert [w["player_id"] for w in out["awards"]["盖楼奖"]] == ["1000000001"]
    assert [p["player_id"] for p in out["participation"]] == ["1000000002", "1000000003"]


def test_participation_includes_keyword_winner_when_enabled():
    """开『中奖者可重复领参与奖』时，关键词奖中奖者也进参与奖名单。"""
    raw = [_raw(1, "红色 " + P1), _raw(2, "乱答 " + P2)]
    awards = [{"name": "答题奖", "rule": "top_floors", "n": 1, "keyword": "红色"}]
    out = server.process_pipeline(raw, _players(P1, P2), "earliest", ["en"], awards,
                                  allow_winner_participation=True)
    assert [w["player_id"] for w in out["awards"]["答题奖"]] == [P1]
    assert {p["player_id"] for p in out["participation"]} == {P1, P2}


def test_wrong_then_right_answered_all_e2e():
    """先错后对 + 全部命中：靠全量留言判答对，代表取答对那条(P1 的第5楼)。"""
    raw = [_raw(1, "不知道 " + P1), _raw(2, "红色 " + P2), _raw(5, "红色 " + P1)]
    awards = [{"name": "全对奖", "rule": "answered_all", "keyword": "红色"}]
    out = server.process_pipeline(raw, _players(P1, P2), "earliest", ["en"], awards)
    winners = out["awards"]["全对奖"]
    assert {w["player_id"] for w in winners} == {P1, P2}
    p1 = next(w for w in winners if w["player_id"] == P1)
    assert p1["order"] == 5


def test_invalid_not_double_counted_for_duplicate_no_record():
    """同一玩家多条留言但 Eastblue 无记录：无效名单按去重口径，只计一次。"""
    raw = [_raw(1, "红色 " + P1), _raw(2, "再来 " + P1)]   # P1 两条，players 里没有 P1
    out = server.process_pipeline(raw, _players(P2), "earliest", ["en"],
                                  [{"name": "答题奖", "rule": "top_floors", "n": 1, "keyword": "红色"}])
    assert [r["player_id"] for r in out["invalid"]] == [P1]
    assert out["invalid"][0]["reject_reason"] == "Eastblue无记录"


def test_answered_wrong_but_won_normal_award_excluded_from_keyword():
    """答错者中了排在前面的普通奖后，也不会再莫名进关键词奖(顺序反过来验证)。"""
    raw = [_raw(1, "乱答 " + P1), _raw(2, "红色 " + P2), _raw(3, "红色 " + P3)]
    awards = [
        {"name": "盖楼奖", "rule": "top_floors", "n": 1},                      # → P1(最早)
        {"name": "答题奖", "rule": "top_floors", "n": 5, "keyword": "红色"},   # → P2, P3
    ]
    out = server.process_pipeline(raw, _players(P1, P2, P3), "earliest", ["en"], awards)
    assert [w["player_id"] for w in out["awards"]["盖楼奖"]] == [P1]
    assert [w["player_id"] for w in out["awards"]["答题奖"]] == [P2, P3]
