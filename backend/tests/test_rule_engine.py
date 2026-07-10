import pytest
from reward_hub.rule_engine import (
    top_floors, top_likes, top_replies, random_pick, run_awards)


def _c(pid, order, likes=0, replies=0):
    return {"player_id": pid, "order": order, "likes": likes, "replies": replies}


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
