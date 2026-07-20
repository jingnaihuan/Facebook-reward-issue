# 第五步「留言时间筛选（逾期判定）」Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在第五步结算发奖新增按留言时间（UTC+0）筛选的「逾期参与」判定，作为高于一切的最高优先级淘汰。

**Architecture:** 后端新增纯函数模块 `time_filter.py`（解析时间 + 按时间窗分区，产出带「逾期参与」原因的无效记录），在 `process_pipeline` 最前面作为第一道闸门接入；前端在第五步奖项列表上方加一块 datetime-local 面板收集筛选条件。默认关闭时行为与现状完全一致。

**Tech Stack:** Python 3.9 标准库 `datetime`/`re`（无三方依赖）；pytest；原生 HTML `<input type="datetime-local">` + 现有前端设计系统。

参考 spec：`docs/superpowers/specs/2026-07-20-overdue-time-filter-design.md`

---

## 文件结构

- **Create** `backend/reward_hub/time_filter.py` — 时间解析 + `filter_by_time` 分区（唯一判定源，纯函数可单测）。
- **Create** `backend/tests/test_time_filter.py` — 模块单元测试。
- **Create** `backend/tests/test_overdue_pipeline.py` — `process_pipeline` 集成测试（优先级/关键词/无时间戳/回归）。
- **Modify** `backend/server.py` — `process_pipeline`（首道闸门 + 返回 `overdue_stats`）、`write_run_log`（记录筛选）、`/api/process`（透传 `time_filter`）、顶部 import。
- **Modify** `frontend/index.html` — CSS（datetime-local 字体 + 面板/摘要样式）、HTML（Step 5 面板）、JS（模式联动 + 校验 + payload + 摘要）。

---

## Task 1: 时间解析 `parse_time`

**Files:**
- Create: `backend/reward_hub/time_filter.py`
- Test: `backend/tests/test_time_filter.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_time_filter.py`：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.build_venv/bin/python -m pytest tests/test_time_filter.py -v`
Expected: FAIL —「ModuleNotFoundError: No module named 'reward_hub.time_filter'」

- [ ] **Step 3: 写最小实现**

创建 `backend/reward_hub/time_filter.py`：

```python
# -*- coding: utf-8 -*-
"""按留言时间筛选：活动时间窗之外的留言判为「逾期参与」（最高优先级淘汰）。

时间基准 UTC+0（Facebook 抓取的 created_time 即 +0000；手工粘贴须自行保证为 UTC+0）。
无法解析时间的留言按「放行」处理（宁放过不错杀），另计数供界面提示。
"""
import datetime
import re

_UTC = datetime.timezone.utc
_FMT = "%Y-%m-%d %H:%M"                         # 展示/原因文案用
_FALLBACK_FMTS = ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d")  # 斜杠等 isoformat 认不出的粘贴格式


def _to_utc(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)            # 无偏移视为 UTC+0
    return dt.astimezone(_UTC)


def parse_time(s):
    """把时间字符串解析为 tz-aware UTC datetime；无法解析返回 None。
    兼容：FB 的 ...+0000 / ...+00:00 / ...Z / 无偏移 / 'YYYY-MM-DD HH:MM[:SS]' / 纯日期 / 斜杠日期。"""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    norm = re.sub(r"[Zz]$", "+00:00", s)
    norm = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", norm)   # +0000 -> +00:00
    try:
        return _to_utc(datetime.datetime.fromisoformat(norm))
    except ValueError:
        pass
    for fmt in _FALLBACK_FMTS:
        try:
            return _to_utc(datetime.datetime.strptime(s, fmt))
        except ValueError:
            continue
    return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.build_venv/bin/python -m pytest tests/test_time_filter.py -v`
Expected: PASS（6 项全绿）

- [ ] **Step 5: 提交**

```bash
git add backend/reward_hub/time_filter.py backend/tests/test_time_filter.py
git commit -m "feat: time_filter.parse_time（UTC+0 多格式时间解析）"
```

---

## Task 2: 时间窗分区 `filter_by_time`

**Files:**
- Modify: `backend/reward_hub/time_filter.py`
- Test: `backend/tests/test_time_filter.py`

- [ ] **Step 1: 追加失败测试**

在 `backend/tests/test_time_filter.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.build_venv/bin/python -m pytest tests/test_time_filter.py -v`
Expected: FAIL —「cannot import name 'filter_by_time'」

- [ ] **Step 3: 写实现**

在 `backend/reward_hub/time_filter.py` 末尾追加：

```python
def _reason(kind, bound_dt):
    """kind='late'（晚于结束）/ 'early'（早于开始）。统一以「逾期参与」开头。"""
    when = bound_dt.strftime(_FMT)
    if kind == "late":
        return "逾期参与（活动时间外·晚于 %s UTC+0）" % when
    return "逾期参与（活动时间外·早于 %s UTC+0）" % when


def filter_by_time(rows, cfg):
    """按时间窗把 rows 分区，返回 (passed, rejected, stats)。
    cfg 为空 / mode 不在 (before/after/between) → 全放行。
    时间窗为闭区间：before(t<=end) / after(t>=start) / between(start<=t<=end)。
    无法解析时间的行一律放行并计入 stats['no_time']。
    缺边界或 start>end 抛 ValueError（安全闸门不静默失效）。"""
    stats = {"overdue": 0, "no_time": 0}
    if not cfg:
        return list(rows), [], stats
    mode = (cfg.get("mode") or "").strip()
    if mode not in ("before", "after", "between"):
        return list(rows), [], stats

    start = parse_time(cfg.get("start")) if mode in ("after", "between") else None
    end = parse_time(cfg.get("end")) if mode in ("before", "between") else None
    if mode == "before" and end is None:
        raise ValueError("时间筛选「之前」模式缺少结束时间")
    if mode == "after" and start is None:
        raise ValueError("时间筛选「之后」模式缺少开始时间")
    if mode == "between" and (start is None or end is None):
        raise ValueError("时间筛选「期间」模式缺少开始或结束时间")
    if mode == "between" and start > end:
        raise ValueError("时间筛选「期间」的开始时间不能晚于结束时间")

    passed, rejected = [], []
    for r in rows:
        t = parse_time(r.get("time"))
        if t is None:
            stats["no_time"] += 1
            passed.append(r)
            continue
        if mode == "before":
            if t <= end:
                passed.append(r)
            else:
                stats["overdue"] += 1
                rejected.append({**r, "reject_reason": _reason("late", end)})
        elif mode == "after":
            if t >= start:
                passed.append(r)
            else:
                stats["overdue"] += 1
                rejected.append({**r, "reject_reason": _reason("early", start)})
        else:  # between
            if t < start:
                stats["overdue"] += 1
                rejected.append({**r, "reject_reason": _reason("early", start)})
            elif t > end:
                stats["overdue"] += 1
                rejected.append({**r, "reject_reason": _reason("late", end)})
            else:
                passed.append(r)
    return passed, rejected, stats
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.build_venv/bin/python -m pytest tests/test_time_filter.py -v`
Expected: PASS（全部 14 项绿）

- [ ] **Step 5: 提交**

```bash
git add backend/reward_hub/time_filter.py backend/tests/test_time_filter.py
git commit -m "feat: time_filter.filter_by_time（三模式闭区间分区 + 逾期原因 + 无时间戳放行计数）"
```

---

## Task 3: 接入 `process_pipeline`（首道闸门 + overdue_stats）

**Files:**
- Modify: `backend/server.py`（import 顶部；`process_pipeline` 107-152）
- Test: `backend/tests/test_overdue_pipeline.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_overdue_pipeline.py`：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.build_venv/bin/python -m pytest tests/test_overdue_pipeline.py -v`
Expected: FAIL —`process_pipeline() got an unexpected keyword argument 'time_filter'`

- [ ] **Step 3a: 加 import**

在 `backend/server.py:15` 之后（`from reward_hub.rule_engine import run_awards` 下一行）加：

```python
from reward_hub.time_filter import filter_by_time
```

- [ ] **Step 3b: 改 `process_pipeline` 签名与函数体**

把 `backend/server.py:107` 的函数签名改为：

```python
def process_pipeline(raw_comments, players, dedup_strategy, target_langs, awards,
                     allow_winner_participation=False, time_filter=None):
```

把函数体开头（原 `invalid = []` / `valid = []` / `for c in raw_comments:` 一段，约 113-124 行）替换为：

```python
    # 最高优先级闸门：时间窗之外的留言直接判「逾期参与」，不进入后续任何判定。
    in_window, overdue, tf_stats = filter_by_time(raw_comments, time_filter)
    for r in overdue:                       # 仅为展示：尽力补 player_id，便于导出/日志核对
        pid = extract_id(r.get("content", ""))
        if pid:
            r["player_id"] = pid
    invalid = list(overdue)
    valid = []                              # 提取到ID的全部留言（未去重，一人可多条）
    for c in in_window:
        content = c.get("content", "")
        pid = extract_id(content)
        if pid:
            valid.append({**c, "player_id": pid})
        elif not str(content).strip():
            invalid.append({**c, "reject_reason": "空内容（图片/动图等，无文字）"})
        else:
            invalid.append({**c, "reject_reason": "无有效ID"})
```

把 `process_pipeline` 的 `return`（约 152 行）改为：

```python
    mode = (time_filter or {}).get("mode") or "off"
    if mode not in ("before", "after", "between"):
        mode = "off"
    return {"awards": result, "participation": participation, "invalid": invalid,
            "overdue_stats": {"mode": mode, **tf_stats}}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.build_venv/bin/python -m pytest tests/test_overdue_pipeline.py -v`
Expected: PASS（5 项全绿）

- [ ] **Step 5: 提交**

```bash
git add backend/server.py backend/tests/test_overdue_pipeline.py
git commit -m "feat: process_pipeline 接入逾期闸门（首道判定 + overdue_stats）"
```

---

## Task 4: 结算日志记录 + `/api/process` 透传

**Files:**
- Modify: `backend/server.py`（`write_run_log` 155-188；`/api/process` 253-257）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_overdue_pipeline.py` 末尾追加：

```python
def test_run_log_records_time_filter(tmp_path, monkeypatch):
    import reward_hub.common as common
    monkeypatch.setattr(common, "work_dir", lambda: str(tmp_path))
    raw = [_raw(1, "1000000001", "2023-05-15T20:00:00+0000")]
    players = _players("1000000001")
    out = server.process_pipeline(raw, players, "all", ["en"], [], time_filter=WIN)
    inputs = {"raw_comments": raw, "players": players, "dedup_strategy": "all",
              "target_langs": ["en"], "awards": [], "time_filter": WIN}
    path = server.write_run_log(inputs, out)
    assert path is not None
    import json
    rec = json.load(open(path, encoding="utf-8"))
    assert rec["时间筛选"]["模式"] == "before"
    assert rec["时间筛选"]["逾期数"] == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.build_venv/bin/python -m pytest tests/test_overdue_pipeline.py::test_run_log_records_time_filter -v`
Expected: FAIL —`KeyError: '时间筛选'`

- [ ] **Step 3a: `write_run_log` 记录筛选**

在 `backend/server.py` 的 `write_run_log` 里，`rec = {...}` 字典构建之后、`logdir = ...` 之前，加：

```python
        tf = inputs.get("time_filter") or {}
        tf_mode = (tf.get("mode") or "off")
        os_stats = out.get("overdue_stats", {})
        rec["时间筛选"] = {
            "模式": tf_mode,
            "开始": tf.get("start", ""),
            "结束": tf.get("end", ""),
            "逾期数": os_stats.get("overdue", 0),
            "无时间戳放行数": os_stats.get("no_time", 0),
        }
```

- [ ] **Step 3b: `/api/process` 透传 `time_filter`**

把 `backend/server.py:253-257` 的 `process_pipeline(...)` 调用改为：

```python
                out = process_pipeline(
                    b["raw_comments"], b.get("players", {}),
                    b.get("dedup_strategy", "earliest"),
                    b.get("target_langs", ["en"]), b.get("awards", []),
                    allow_winner_participation=bool(b.get("allow_winner_participation")),
                    time_filter=b.get("time_filter"))
```

（`write_run_log(b, out)` 已传整个 body `b`，其中含 `time_filter`，无需改动。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.build_venv/bin/python -m pytest tests/test_overdue_pipeline.py -v`
Expected: PASS（6 项全绿）

- [ ] **Step 5: 提交**

```bash
git add backend/server.py backend/tests/test_overdue_pipeline.py
git commit -m "feat: 结算日志记录时间筛选 + /api/process 透传 time_filter"
```

---

## Task 5: 前端 CSS（datetime-local 字体一致 + 面板/摘要样式）

**Files:**
- Modify: `frontend/index.html`（输入框规则 ~179；新增样式块）

- [ ] **Step 1: 让 datetime-local 走统一字体与外观**

把 `frontend/index.html:179` 的选择器：

```css
  input[type=text], input[type=number], select, textarea {
```

改为（追加三个类型，使其获得同样的边框/圆角/`font-family: var(--mono)`）：

```css
  input[type=text], input[type=number], input[type="datetime-local"], input[type="date"], input[type="time"], select, textarea {
```

- [ ] **Step 2: 新增面板 + 摘要样式**

在 `frontend/index.html` 的 `</style>` 之前加：

```css
  /* ── 第五步·时间筛选面板 ── */
  .tf-panel { background: var(--panel-2); border: 1px solid var(--border); border-radius: 14px; padding: 15px 17px; margin-bottom: 16px; }
  .tf-panel .tf-head { display: flex; align-items: center; gap: 9px; font-family: var(--display); font-weight: 700; font-size: 14px; color: var(--text); }
  .tf-panel .tf-head .ic { font-size: 15px; }
  .tf-utc { font-family: var(--mono); background: var(--gold-dim); color: var(--gold); padding: 1px 7px; border-radius: 6px; font-size: 10.5px; letter-spacing: .04em; }
  .tf-row { display: flex; align-items: flex-end; gap: 14px; flex-wrap: wrap; margin-top: 13px; }
  .tf-field { display: flex; flex-direction: column; }
  .tf-field .fld { margin-bottom: 6px; }
  .tf-field input[type="datetime-local"] { width: 210px; }
  .tf-field select { min-width: 240px; }
  .tf-tilde { align-self: center; color: var(--muted-2); font-weight: 700; padding: 0 2px; margin-top: 18px; }
  .tf-note { font-size: 11.5px; line-height: 1.6; color: var(--muted); margin-top: 12px; }
  .tf-summary { background: var(--gold-dim); border: 1px solid var(--border); border-left: 3px solid var(--gold); border-radius: 9px; padding: 9px 13px; margin-bottom: 14px; font-size: 12.5px; color: var(--text); font-family: var(--mono); }
```

- [ ] **Step 3: 提交**

```bash
git add frontend/index.html
git commit -m "style: datetime-local 字体统一(Mac/Win) + 时间筛选面板/摘要样式"
```

（视觉验收在 Task 8 实机截图；此处不单测。）

---

## Task 6: 前端 HTML 面板（Step 5 奖项列表上方）

**Files:**
- Modify: `frontend/index.html`（Step 5，`<div id="awardList"></div>` 之前，约 677 行）

- [ ] **Step 1: 插入面板**

在 `frontend/index.html` 的 `<div id="awardList"></div>`（约 677 行）**之前**插入：

```html
      <div class="tf-panel" id="tfPanel">
        <div class="tf-head"><span class="ic">⏱</span> 时间筛选 · 逾期判定 <span class="tf-utc">UTC+0</span></div>
        <div class="tf-row">
          <div class="tf-field">
            <label class="fld">判定模式</label>
            <select id="tfMode">
              <option value="off">关闭（不按时间筛选）</option>
              <option value="before">某时间之前有效（此后为逾期）</option>
              <option value="after">某时间之后有效（此前无效）</option>
              <option value="between">某时间段内有效（窗外无效）</option>
            </select>
          </div>
          <div class="tf-field" id="tfStartWrap" style="display:none;">
            <label class="fld" id="tfStartLbl">开始时间</label>
            <input type="datetime-local" id="tfStart" />
          </div>
          <span class="tf-tilde" id="tfTilde" style="display:none;">~</span>
          <div class="tf-field" id="tfEndWrap" style="display:none;">
            <label class="fld" id="tfEndLbl">结束时间</label>
            <input type="datetime-local" id="tfEnd" />
          </div>
        </div>
        <div class="tf-note">🕒 时间基准 <b>UTC+0</b>：Facebook 抓取的留言时间即为 UTC+0；手工粘贴导入时请确保填入的时间也是 UTC+0。窗口外的留言无论 ID / 答案是否有效，一律判「逾期参与」（优先级高于一切发奖判定）。</div>
      </div>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/index.html
git commit -m "feat: 第五步新增时间筛选面板(HTML)"
```

---

## Task 7: 前端 JS（模式联动 + 校验 + payload + 摘要）

**Files:**
- Modify: `frontend/index.html`（Step 5 脚本区新增联动；`btnProcess` onclick 校验 + payload；`renderResults` 摘要）

- [ ] **Step 1: 模式联动**

在 `frontend/index.html` 脚本里 `$("btnProcess").onclick = async () => {`（约 1420 行）**之前**插入：

```javascript
/* 时间筛选：按模式显示对应的时间输入框并调整标签 */
function tfSync() {
  const m = $("tfMode").value;
  const showStart = (m === "after" || m === "between");
  const showEnd = (m === "before" || m === "between");
  $("tfStartWrap").style.display = showStart ? "" : "none";
  $("tfEndWrap").style.display = showEnd ? "" : "none";
  $("tfTilde").style.display = (m === "between") ? "" : "none";
  if (m === "before") $("tfEndLbl").textContent = "结束时间（此后视为逾期）";
  if (m === "after") $("tfStartLbl").textContent = "开始时间（此前视为无效）";
  if (m === "between") { $("tfStartLbl").textContent = "开始时间"; $("tfEndLbl").textContent = "结束时间"; }
}
$("tfMode").onchange = tfSync;
tfSync();
```

- [ ] **Step 2: 结算校验 + 收集 cfg**

在 `frontend/index.html` 的 `btnProcess` onclick 里，award 校验块结束后（约 1446 行 `}` 之后）、`const note = $("procNote"); note.className = "note"; note.textContent = "结算中…";`（约 1447 行）**之前**插入：

```javascript
  // 时间筛选（最高优先级逾期判定）：校验并收集配置
  const tfMode = $("tfMode").value;
  let timeFilter = null;
  if (tfMode !== "off") {
    const tfStart = $("tfStart").value, tfEnd = $("tfEnd").value;
    const failTf = (msg) => { const nt = $("procNote"); nt.className = "flash err"; nt.textContent = msg; toast("时间筛选未填完整", "err"); };
    if ((tfMode === "after" || tfMode === "between") && !tfStart) { failTf("请填写时间筛选的开始时间，或将「判定模式」设为关闭。"); return; }
    if ((tfMode === "before" || tfMode === "between") && !tfEnd) { failTf("请填写时间筛选的结束时间，或将「判定模式」设为关闭。"); return; }
    if (tfMode === "between" && tfStart > tfEnd) { failTf("时间筛选：开始时间不能晚于结束时间。"); return; }
    timeFilter = { mode: tfMode, start: tfStart || null, end: tfEnd || null };
  }
```

- [ ] **Step 3: 加入 payload**

把 `frontend/index.html` payload 对象（约 1453-1460）里加一行 `time_filter`：

```javascript
  const payload = {
    raw_comments: state.raw,
    players: state.players,
    dedup_strategy: $("dedupSel").value,
    target_langs: getChecked($("targetLangs")),
    awards,
    allow_winner_participation: allowWinnerPart,
    time_filter: timeFilter,
  };
```

- [ ] **Step 4: 结果区摘要**

在 `frontend/index.html` 的 `function renderResults(res) {` 里，`const box = $("results"); clear(box);`（约 1513 行）**之后**插入：

```javascript
  // 时间筛选摘要（最高优先级逾期判定）：模式≠关闭时展示，含无时间戳放行提示
  const os = res.overdue_stats;
  if (os && os.mode && os.mode !== "off") {
    const label = { before: "某时间之前有效", after: "某时间之后有效", between: "某时间段内有效" }[os.mode] || os.mode;
    const parts = ["⏱ 时间筛选：" + label, "逾期 " + os.overdue + " 条"];
    if (os.no_time > 0) parts.push("无时间戳放行 " + os.no_time + " 条");
    box.appendChild(h("div", { class: "tf-summary" }, parts.join("　·　")));
  }
```

- [ ] **Step 5: 提交**

```bash
git add frontend/index.html
git commit -m "feat: 第五步时间筛选 JS（模式联动 + 校验 + payload + 结果摘要）"
```

---

## Task 8: 全量回归 + 实机测试

**Files:** 无（仅运行验证）

- [ ] **Step 1: 后端全量回归**

Run: `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.build_venv/bin/python -m pytest -q`
Expected: 全部 PASS（既有 + 新增 test_time_filter / test_overdue_pipeline）。若有红，修到全绿再继续。

- [ ] **Step 2: 起本机服务**

用 preview_start 起后台（`.claude/launch.json` 若无则新建，命令为 `../.build_venv/bin/python backend/server.py` 或仓库既有启动方式，端口 18765），浏览器开 `http://localhost:18765`。

- [ ] **Step 3: 造数据走通四种模式**

第一步「粘贴」导入以下（制表符/逗号分隔：序号,留言内容,按赞,时间）：
```
1,帮我发奖 1000000001,3,2026-07-15T10:00:00+0000
2,帮我发奖 1000000002,1,2026-07-15T20:00:00+0000
3,帮我发奖 1000000003,0,2026-07-15T09:00:00+0000
4,没有ID的很晚留言,0,2026-07-15T23:00:00+0000
5,帮我发奖 1000000004 没有时间,0,
```
（第三步玩家表可用 `all` 语言或直接造 Eastblue 导入；若跑通流程有阻力，可仅验证第五步 UI + 结算接口返回。）

逐一验证：
- 模式「某时间之前」结束=`2026-07-15T18:00`：留言 2、4 判「逾期参与（…晚于…）」，留言 5（无时间）放行；摘要显示「逾期 2 条 · 无时间戳放行 1 条」。
- 模式「某时间之后」开始=`2026-07-15T18:00`：留言 1、3 判「逾期参与（…早于…）」。
- 模式「某时间段内」`10:00~18:00`：留言 1 界内；2/3/4 逾期。
- 模式「关闭」：无逾期，行为与改动前一致。

- [ ] **Step 4: 核对无效名单 + 优先级 + 导出**

- 无效名单「原因」列显示「逾期参与（…UTC+0）」。
- 留言 4（无ID且逾期）原因是「逾期参与」而非「无有效ID」。
- 点「导出 xlsx」，打开「无效」sheet 确认逾期记录与原因在列。

- [ ] **Step 5: 视觉与字体验收（截图）**

- computer screenshot 第五步面板：布局整齐、UTC+0 标记清晰、模式切换时输入框正确显隐。
- javascript_tool 取 `getComputedStyle($("tfStart")).fontFamily`，确认与相邻 `#dedupSel`/数字输入框一致（Mac 下为 SF Mono 栈）。
- read_console_messages 确认无报错。

- [ ] **Step 6: Windows 验收要点（本机不跑，追加到清单）**

在 `Windows验收清单.md` 追加一节「时间筛选」：面板显示正常、日期输入框字体为微软雅黑（与其它输入框一致）、四模式结算与无效原因正确、导出无效 sheet 正确。

- [ ] **Step 7: 收尾提交**

```bash
git add -A && git commit -m "test: 时间筛选实机验收 + Windows 验收清单补充"
```

---

## Self-Review（作者自检，已完成）

**Spec coverage：** 三模式(Task 2/6/7) ✓；逾期最高优先级(Task 3 首道闸门) ✓；原因统一「逾期参与」+边界(Task 2 `_reason`) ✓；无时间戳放行+计数(Task 2/3/7) ✓；UTC+0 批注(Task 6) ✓；字体一致 Mac/Win(Task 5) ✓；关键词奖排除逾期(Task 3 测试) ✓；日志记录(Task 4) ✓；不破坏既有(Task 3 默认 None + Task 8 回归) ✓；导出无效 sheet(Task 8 复用既有) ✓；美观(Task 5/8) ✓。

**Placeholder scan：** 无 TBD/TODO；每个改码步骤均含完整代码。

**Type consistency：** `filter_by_time(rows, cfg)->(passed,rejected,stats)`、`parse_time(s)`、`_reason(kind,bound_dt)`、返回键 `overdue_stats={mode,overdue,no_time}`、payload 键 `time_filter={mode,start,end}`、DOM id `tfMode/tfStart/tfEnd/tfStartWrap/tfEndWrap/tfTilde/tfStartLbl/tfEndLbl` 在各 Task 间一致。
