import pytest
from reward_hub.rule_engine import (
    top_floors, top_likes, top_replies, random_pick, run_awards)


def _c(pid, order, likes=0, replies=0, content=""):
    return {"player_id": pid, "order": order, "likes": likes,
            "replies": replies, "content": content}


def test_top_floors():
    rows = [_c("a", 3), _c("b", 1), _c("c", 2)]
    assert [r["player_id"] for r in top_floors(rows, 2)] == ["b", "c"]


def test_top_floors_n_exceeds_len():
    rows = [_c("a", 1)]
    assert len(top_floors(rows, 5)) == 1


def test_top_likes_desc():
    rows = [_c("a", 1, likes=2), _c("b", 2, likes=9), _c("c", 3, likes=5)]
    assert [r["player_id"] for r in top_likes(rows, 2)] == ["b", "c"]


def test_top_likes_tie_breaks_by_order():
    rows = [_c("a", 5, likes=3), _c("b", 2, likes=3)]
    assert [r["player_id"] for r in top_likes(rows, 1)] == ["b"]


def test_top_replies_desc():
    rows = [_c("a", 1, replies=1), _c("b", 2, replies=8)]
    assert [r["player_id"] for r in top_replies(rows, 1)] == ["b"]


def test_random_pick_reproducible():
    rows = [_c(str(i), i) for i in range(10)]
    a = [r["player_id"] for r in random_pick(rows, 3, seed=42)]
    b = [r["player_id"] for r in random_pick(rows, 3, seed=42)]
    assert a == b and len(a) == 3


def test_random_pick_different_seed_differs():
    rows = [_c(str(i), i) for i in range(20)]
    a = [r["player_id"] for r in random_pick(rows, 5, seed=1)]
    b = [r["player_id"] for r in random_pick(rows, 5, seed=2)]
    assert a != b


def test_run_awards_excludes_previous_winners():
    rows = [_c(str(i), i) for i in range(1, 6)]  # order 1..5
    awards = [
        {"name": "先锋奖", "rule": "top_floors", "n": 2},
        {"name": "参与奖", "rule": "top_floors", "n": 2},
    ]
    result, remaining = run_awards(rows, awards)
    assert [r["player_id"] for r in result["先锋奖"]] == ["1", "2"]
    assert [r["player_id"] for r in result["参与奖"]] == ["3", "4"]
    assert [r["player_id"] for r in remaining] == ["5"]


def test_run_awards_random_uses_seed():
    rows = [_c(str(i), i) for i in range(1, 11)]
    awards = [{"name": "抽选", "rule": "random_pick", "n": 3, "seed": 7}]
    r1, _ = run_awards(rows, awards)
    r2, _ = run_awards(rows, awards)
    assert [x["player_id"] for x in r1["抽选"]] == [x["player_id"] for x in r2["抽选"]]


def test_run_awards_empty_is_universal_everyone_remains():
    """普惠奖 = 不传任何奖项：全部有效参与者留在 remaining（= 全员发奖名单）。"""
    rows = [_c(str(i), i) for i in range(1, 6)]
    result, remaining = run_awards(rows, [])
    assert result == {}
    assert [r["player_id"] for r in remaining] == ["1", "2", "3", "4", "5"]


@pytest.mark.parametrize("bad_n", [0, -1, None, 1.5, True])
def test_run_awards_rejects_non_positive_n(bad_n):
    """非普惠规则的数量必须为正整数，否则拒绝（第二道防线，防前端被绕过）。"""
    rows = [_c(str(i), i) for i in range(1, 6)]
    with pytest.raises(ValueError):
        run_awards(rows, [{"name": "前N楼", "rule": "top_floors", "n": bad_n}])


# ── 关键词奖 ────────────────────────────────────────────────────────
def _kc(pid, order, content, likes=0, replies=0):
    return _c(pid, order, likes=likes, replies=replies, content=content)


def test_keyword_award_selects_only_correct():
    """只在答对的人里选；答错的人不进关键词奖池。"""
    rows = [_kc("a", 1, "红色"), _kc("b", 2, "蓝色"), _kc("c", 3, "红色")]
    awards = [{"name": "答题奖", "rule": "top_floors", "n": 5, "keyword": "红色"}]
    result, _ = run_awards(rows, awards, all_comments=rows)
    assert [w["player_id"] for w in result["答题奖"]] == ["a", "c"]


def test_keyword_top_floors_uses_earliest_correct_across_all_comments():
    """先错后对：代表留言取『最早答对』那条，而非去重后保留的错误那条。"""
    deduped = [_kc("a", 1, "错"), _kc("b", 2, "红色")]        # 去重(最早)留下 a 的错误留言
    all_comments = [_kc("a", 1, "错"), _kc("b", 2, "红色"), _kc("a", 5, "红色")]
    awards = [{"name": "答题奖", "rule": "top_floors", "n": 2, "keyword": "红色"}]
    result, _ = run_awards(deduped, awards, all_comments=all_comments)
    winners = result["答题奖"]
    assert [w["player_id"] for w in winners] == ["b", "a"]     # 按答对楼层排序
    a_win = next(w for w in winners if w["player_id"] == "a")
    assert a_win["order"] == 5 and a_win["content"] == "红色"   # 用的是答对那条


def test_keyword_top_likes_uses_highest_liked_correct():
    """点赞最高 + 答对：代表取该玩家点赞最高的那条答对留言。"""
    all_comments = [_kc("a", 1, "红色", likes=2), _kc("a", 5, "红色", likes=50),
                    _kc("b", 2, "红色", likes=10)]
    awards = [{"name": "答题奖", "rule": "top_likes", "n": 1, "keyword": "红色"}]
    result, _ = run_awards(all_comments, awards, all_comments=all_comments)
    winners = result["答题奖"]
    assert [w["player_id"] for w in winners] == ["a"]
    assert winners[0]["likes"] == 50 and winners[0]["order"] == 5


def test_keyword_answered_all_gives_everyone_correct():
    """全部命中(答对即得)：所有答对的人都发，不限人数，按楼层排序。"""
    all_comments = [_kc("a", 1, "红色"), _kc("b", 2, "错"), _kc("c", 3, "红色")]
    awards = [{"name": "全对奖", "rule": "answered_all", "keyword": "红色"}]
    result, _ = run_awards(all_comments, awards, all_comments=all_comments)
    assert [w["player_id"] for w in result["全对奖"]] == ["a", "c"]


def test_answered_all_requires_keyword():
    rows = [_kc("a", 1, "红色")]
    with pytest.raises(ValueError):
        run_awards(rows, [{"name": "全对奖", "rule": "answered_all"}], all_comments=rows)


def test_keyword_award_shares_one_per_person_with_normal_awards():
    """关键词奖中奖者从后续普通奖池剔除（一人一档跨关键词/普通奖生效）。"""
    rows = [_kc("a", 1, "红色"), _kc("b", 2, "红色"), _kc("c", 3, "错"), _kc("d", 4, "错")]
    awards = [
        {"name": "答题奖", "rule": "top_floors", "n": 1, "keyword": "红色"},  # → a
        {"name": "盖楼奖", "rule": "top_floors", "n": 2},                      # → b, c
    ]
    result, remaining = run_awards(rows, awards, all_comments=rows)
    assert [w["player_id"] for w in result["答题奖"]] == ["a"]
    assert [w["player_id"] for w in result["盖楼奖"]] == ["b", "c"]
    assert [r["player_id"] for r in remaining] == ["d"]


def test_keyword_award_shortfall_no_error():
    """答对人数 < N：返回全部答对者，不报错。"""
    rows = [_kc("a", 1, "红色"), _kc("b", 2, "错")]
    awards = [{"name": "答题奖", "rule": "top_floors", "n": 5, "keyword": "红色"}]
    result, _ = run_awards(rows, awards, all_comments=rows)
    assert [w["player_id"] for w in result["答题奖"]] == ["a"]


def test_keyword_award_id_digits_not_false_positive():
    """正答是数字时，玩家ID里的同数字不算答对。"""
    rows = [_kc("1200000012", 1, "1200000012"),          # 只有ID，没真答
            _kc("1000000034", 2, "答案12 1000000034")]    # 正文里有 12
    awards = [{"name": "答题奖", "rule": "top_floors", "n": 5, "keyword": "12"}]
    result, _ = run_awards(rows, awards, all_comments=rows)
    assert [w["player_id"] for w in result["答题奖"]] == ["1000000034"]


def test_keyword_random_reproducible():
    rows = [_kc(str(i), i, "红色") for i in range(1, 11)]
    awards = [{"name": "答题抽", "rule": "random_pick", "n": 3, "seed": 9, "keyword": "红色"}]
    r1, _ = run_awards(rows, awards, all_comments=rows)
    r2, _ = run_awards(rows, awards, all_comments=rows)
    assert [w["player_id"] for w in r1["答题抽"]] == [w["player_id"] for w in r2["答题抽"]]


def test_keyword_multi_keyword_or():
    rows = [_kc("a", 1, "我选red"), _kc("b", 2, "蓝色"), _kc("c", 3, "红色")]
    awards = [{"name": "答题奖", "rule": "top_floors", "n": 5, "keyword": "红色, red"}]
    result, _ = run_awards(rows, awards, all_comments=rows)
    assert [w["player_id"] for w in result["答题奖"]] == ["a", "c"]


def test_empty_keyword_behaves_as_normal_award():
    """关键词留空 = 普通奖（在去重池上按规则选，不做答对过滤）。"""
    rows = [_c(str(i), i) for i in range(1, 6)]
    awards = [{"name": "盖楼奖", "rule": "top_floors", "n": 2, "keyword": ""}]
    result, _ = run_awards(rows, awards)
    assert [w["player_id"] for w in result["盖楼奖"]] == ["1", "2"]


def test_keyword_fallback_to_rows_when_no_all_comments():
    """未传 all_comments 时，关键词奖回退到在去重池那条上匹配。"""
    rows = [_kc("a", 1, "红色"), _kc("b", 2, "错")]
    awards = [{"name": "答题奖", "rule": "top_floors", "n": 5, "keyword": "红色"}]
    result, _ = run_awards(rows, awards)
    assert [w["player_id"] for w in result["答题奖"]] == ["a"]


# ── 点赞/回复最高：>0 才有资格（0 赞/0 回复不凑数）──────────────────
def test_top_likes_requires_positive_likes():
    """点赞最高奖只发给真点过赞的人；不足 N 时给实际人数，不用 0 赞的补位。"""
    rows = [_c("a", 1, likes=3), _c("b", 2, likes=1),
            _c("c", 3, likes=0), _c("d", 4, likes=0)]
    assert [r["player_id"] for r in top_likes(rows, 4)] == ["a", "b"]


def test_top_likes_all_zero_returns_empty():
    rows = [_c("a", 1, likes=0), _c("b", 2, likes=0)]
    assert top_likes(rows, 3) == []


def test_top_replies_requires_positive_replies():
    rows = [_c("a", 1, replies=2), _c("b", 2, replies=0), _c("c", 3, replies=5)]
    assert [r["player_id"] for r in top_replies(rows, 3)] == ["c", "a"]


def test_top_likes_positive_filter_via_run_awards():
    """经 run_awards 结算时同样只选 >0，落选者留在 remaining（可进参与奖）。"""
    rows = [_c(str(i), i, likes=(3 if i <= 2 else 0)) for i in range(1, 6)]
    result, remaining = run_awards(rows, [{"name": "点赞奖", "rule": "top_likes", "n": 4}])
    assert [w["player_id"] for w in result["点赞奖"]] == ["1", "2"]
    assert [r["player_id"] for r in remaining] == ["3", "4", "5"]


# ── 关键词奖：更多交互维度 ──────────────────────────────────────────
def test_two_keyword_awards_share_won_ids():
    """连续两个关键词奖：先中的人不进第二个关键词奖。"""
    rows = [_kc("a", 1, "红色"), _kc("b", 2, "红色"), _kc("c", 3, "红色")]
    awards = [
        {"name": "一等", "rule": "top_floors", "n": 1, "keyword": "红色"},   # a
        {"name": "二等", "rule": "top_floors", "n": 2, "keyword": "红色"},   # b, c
    ]
    result, _ = run_awards(rows, awards, all_comments=rows)
    assert [w["player_id"] for w in result["一等"]] == ["a"]
    assert [w["player_id"] for w in result["二等"]] == ["b", "c"]


def test_answered_all_excludes_already_won():
    """全部命中排在普通奖之后：已中普通奖的人不再进全部命中。"""
    rows = [_kc("a", 1, "红色"), _kc("b", 2, "红色"), _kc("c", 3, "红色")]
    awards = [
        {"name": "盖楼", "rule": "top_floors", "n": 1},                 # a
        {"name": "全对", "rule": "answered_all", "keyword": "红色"},     # b, c
    ]
    result, _ = run_awards(rows, awards, all_comments=rows)
    assert [w["player_id"] for w in result["盖楼"]] == ["a"]
    assert [w["player_id"] for w in result["全对"]] == ["b", "c"]


def test_answered_all_first_then_normal_excludes_winners():
    """全部命中排在前：答对的人全被拿走，普通奖只能从没答对的人里选。"""
    rows = [_kc("a", 1, "红色"), _kc("b", 2, "红色"), _kc("c", 3, "错"), _kc("d", 4, "错")]
    awards = [
        {"name": "全对", "rule": "answered_all", "keyword": "红色"},     # a, b
        {"name": "盖楼", "rule": "top_floors", "n": 3},                 # c, d
    ]
    result, remaining = run_awards(rows, awards, all_comments=rows)
    assert [w["player_id"] for w in result["全对"]] == ["a", "b"]
    assert [w["player_id"] for w in result["盖楼"]] == ["c", "d"]
    assert remaining == []


def test_keyword_top_replies_uses_highest_reply_correct():
    """回复最高+答对：代表取该玩家回复最高的那条答对留言（与点赞奖对称）。"""
    all_comments = [_kc("a", 1, "红色", replies=1), _kc("a", 5, "红色", replies=40),
                    _kc("b", 2, "红色", replies=10)]
    awards = [{"name": "答题回复奖", "rule": "top_replies", "n": 1, "keyword": "红色"}]
    result, _ = run_awards(all_comments, awards, all_comments=all_comments)
    w = result["答题回复奖"]
    assert [x["player_id"] for x in w] == ["a"]
    assert w[0]["replies"] == 40 and w[0]["order"] == 5


def test_keyword_top_likes_excludes_zero_like_correct():
    """点赞最高+答对：答对但代表留言 0 赞的人没资格（与 >0 规则一致）。"""
    all_comments = [_kc("a", 1, "红色", likes=0), _kc("b", 2, "红色", likes=5)]
    awards = [{"name": "答题点赞奖", "rule": "top_likes", "n": 5, "keyword": "红色"}]
    result, _ = run_awards(all_comments, awards, all_comments=all_comments)
    assert [w["player_id"] for w in result["答题点赞奖"]] == ["b"]


def test_representative_tie_breaks_by_earliest_when_likes_equal():
    """同一玩家多条答对留言点赞相同 → 代表取更早那条。"""
    all_comments = [_kc("a", 5, "红色", likes=3), _kc("a", 2, "红色", likes=3)]
    awards = [{"name": "答题点赞奖", "rule": "top_likes", "n": 1, "keyword": "红色"}]
    result, _ = run_awards(all_comments, awards, all_comments=all_comments)
    assert result["答题点赞奖"][0]["order"] == 2


def test_answered_all_zero_correct_empty_no_error():
    rows = [_kc("a", 1, "错"), _kc("b", 2, "错")]
    result, remaining = run_awards(
        rows, [{"name": "全对", "rule": "answered_all", "keyword": "红色"}], all_comments=rows)
    assert result["全对"] == []
    assert [r["player_id"] for r in remaining] == ["a", "b"]
