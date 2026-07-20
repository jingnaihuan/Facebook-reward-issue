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
