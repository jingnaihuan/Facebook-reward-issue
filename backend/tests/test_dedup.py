from reward_hub.dedup import dedup


def _c(pid, order, likes=0):
    return {"player_id": pid, "order": order, "likes": likes,
            "replies": 0, "time": "", "content": ""}


def test_earliest_keeps_min_order():
    rows = [_c("1000000001", 5), _c("1000000001", 2), _c("1000000002", 3)]
    out = dedup(rows, "earliest")
    assert len(out) == 2
    got = {r["player_id"]: r["order"] for r in out}
    assert got == {"1000000001": 2, "1000000002": 3}


def test_all_keeps_everything():
    rows = [_c("1000000001", 5), _c("1000000001", 2)]
    assert len(dedup(rows, "all")) == 2


def test_best_likes_keeps_highest_like():
    rows = [_c("1000000001", 5, likes=9), _c("1000000001", 2, likes=1)]
    out = dedup(rows, "best_likes")
    assert len(out) == 1
    assert out[0]["order"] == 5 and out[0]["likes"] == 9


def test_best_likes_tie_breaks_by_order():
    rows = [_c("1000000001", 5, likes=3), _c("1000000001", 2, likes=3)]
    out = dedup(rows, "best_likes")
    assert len(out) == 1 and out[0]["order"] == 2


def test_output_sorted_by_order():
    rows = [_c("1000000003", 9), _c("1000000001", 2), _c("1000000002", 5)]
    out = dedup(rows, "earliest")
    assert [r["order"] for r in out] == [2, 5, 9]
