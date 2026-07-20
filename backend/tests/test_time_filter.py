# -*- coding: utf-8 -*-
import datetime
from reward_hub.time_filter import parse_time

UTC = datetime.timezone.utc


def test_parse_fb_plus0000():
    assert parse_time("2017-06-06T18:04:10+0000") == \
        datetime.datetime(2017, 6, 6, 18, 4, 10, tzinfo=UTC)


def test_parse_colon_offset_and_z():
    assert parse_time("2023-05-15T10:30:00+00:00") == \
        datetime.datetime(2023, 5, 15, 10, 30, tzinfo=UTC)
    assert parse_time("2023-05-15T10:30:00Z") == \
        datetime.datetime(2023, 5, 15, 10, 30, tzinfo=UTC)


def test_parse_naive_treated_as_utc():
    assert parse_time("2026-07-15T18:00") == \
        datetime.datetime(2026, 7, 15, 18, 0, tzinfo=UTC)
    assert parse_time("2023-05-15 10:30:00") == \
        datetime.datetime(2023, 5, 15, 10, 30, tzinfo=UTC)


def test_parse_date_only_and_slash():
    assert parse_time("2023-05-15") == \
        datetime.datetime(2023, 5, 15, 0, 0, tzinfo=UTC)
    assert parse_time("2023/05/15 10:30") == \
        datetime.datetime(2023, 5, 15, 10, 30, tzinfo=UTC)


def test_parse_offset_east_converts_to_utc():
    # +08:00 的 18:00 == UTC 10:00
    assert parse_time("2023-05-15T18:00:00+08:00") == \
        datetime.datetime(2023, 5, 15, 10, 0, tzinfo=UTC)


def test_parse_unparseable_returns_none():
    for bad in [None, "", "   ", "乱码abc", "not-a-time"]:
        assert parse_time(bad) is None


from reward_hub.time_filter import filter_by_time


def _row(order, time, content="帮我发奖 1000000001"):
    return {"order": order, "content": content, "likes": 0, "replies": 0, "time": time}


def test_off_or_none_passes_all():
    rows = [_row(1, "2023-05-15T10:00:00+0000")]
    for cfg in (None, {}, {"mode": "off"}, {"mode": ""}):
        passed, rejected, stats = filter_by_time(rows, cfg)
        assert len(passed) == 1 and rejected == []
        assert stats == {"overdue": 0, "no_time": 0}


def test_before_mode_rejects_late_inclusive_boundary():
    rows = [_row(1, "2023-05-15T17:59:00+0000"),   # 界内
            _row(2, "2023-05-15T18:00:00+0000"),   # 卡边界 = 有效（闭区间）
            _row(3, "2023-05-15T18:00:01+0000")]   # 逾期
    passed, rejected, stats = filter_by_time(rows, {"mode": "before", "end": "2023-05-15T18:00"})
    assert [r["order"] for r in passed] == [1, 2]
    assert [r["order"] for r in rejected] == [3]
    assert "逾期参与" in rejected[0]["reject_reason"]
    assert "晚于" in rejected[0]["reject_reason"]
    assert stats == {"overdue": 1, "no_time": 0}


def test_after_mode_rejects_early():
    rows = [_row(1, "2023-05-15T09:59:00+0000"),   # 太早
            _row(2, "2023-05-15T10:00:00+0000")]   # 卡边界 = 有效
    passed, rejected, stats = filter_by_time(rows, {"mode": "after", "start": "2023-05-15T10:00"})
    assert [r["order"] for r in passed] == [2]
    assert [r["order"] for r in rejected] == [1]
    assert "逾期参与" in rejected[0]["reject_reason"] and "早于" in rejected[0]["reject_reason"]
    assert stats["overdue"] == 1


def test_between_mode_rejects_both_sides():
    rows = [_row(1, "2023-05-15T09:00:00+0000"),   # 早于开始
            _row(2, "2023-05-15T12:00:00+0000"),   # 界内
            _row(3, "2023-05-15T20:00:00+0000")]   # 晚于结束
    passed, rejected, stats = filter_by_time(
        rows, {"mode": "between", "start": "2023-05-15T10:00", "end": "2023-05-15T18:00"})
    assert [r["order"] for r in passed] == [2]
    assert {r["order"] for r in rejected} == {1, 3}
    assert stats["overdue"] == 2


def test_no_time_rows_pass_and_counted():
    rows = [_row(1, ""), _row(2, "乱码"), _row(3, "2023-05-15T20:00:00+0000")]
    passed, rejected, stats = filter_by_time(rows, {"mode": "before", "end": "2023-05-15T18:00"})
    assert {r["order"] for r in passed} == {1, 2}      # 无时间戳放行
    assert [r["order"] for r in rejected] == [3]
    assert stats == {"overdue": 1, "no_time": 2}


def test_missing_bound_raises():
    import pytest
    with pytest.raises(ValueError):
        filter_by_time([], {"mode": "before"})
    with pytest.raises(ValueError):
        filter_by_time([], {"mode": "after"})
    with pytest.raises(ValueError):
        filter_by_time([], {"mode": "between", "start": "2023-05-15T10:00"})


def test_between_start_after_end_raises():
    import pytest
    with pytest.raises(ValueError):
        filter_by_time([], {"mode": "between", "start": "2023-05-15T18:00", "end": "2023-05-15T10:00"})


def test_rejected_row_preserves_original_fields():
    rows = [_row(7, "2023-05-15T20:00:00+0000", content="留言X 1000000009")]
    _, rejected, _ = filter_by_time(rows, {"mode": "before", "end": "2023-05-15T18:00"})
    assert rejected[0]["order"] == 7
    assert rejected[0]["content"] == "留言X 1000000009"
