# 社群互动发奖中台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「抓 FB 留言 → 提取玩家 ID → 拉 Eastblue 玩家信息 → 按语言筛选 → 按发奖规则出名单 → 导出多 sheet」整条发奖流程收进一个本地网页中台。

**Architecture:** 复用 LocoFlow 本地工具模式——Python 标准库 `http.server`（无 web 框架）跑本地服务 + 单页前端向导；纯逻辑（ID 提取 / 去重 / 规则引擎 / 导出）做成可单测的模块；Eastblue 下载和 FB 抓取分别用 Playwright 和浏览器端 Graph API 接入；配置存本地 JSON 支持多预设。

**Tech Stack:** Python 3.9+（标准库 http.server）、openpyxl（xlsx 读写）、playwright（Eastblue 自动下载）、pytest（测试）、原生 HTML/CSS/JS 前端。

---

## 文件结构

```
Projects/社群互动发奖中台/
  backend/
    server.py                      # 本地服务：serve 前端 + /api/* 路由
    requirements.txt
    reward_hub/
      __init__.py
      common.py                    # app_data_dir、JSON load/save、emit/log
      extract_id.py                # 玩家 ID 提取（VBA 正则同款）
      dedup.py                     # 去重（最早/全部/最优）
      rule_engine.py               # 前N楼/随机抽/点赞最高/回复最高 + 奖项排除
      language_filter.py           # 按语言筛选
      export.py                    # 多 sheet xlsx 导出
      eastblue_download.py         # Playwright 打开链接自动下载 xlsx（Phase 2）
      eastblue_parse.py            # 解析 Eastblue 导出 xlsx + 按 ID 匹配（Phase 2）
      config_store.py              # 预设/默认配置持久化
    tests/
      test_extract_id.py
      test_dedup.py
      test_rule_engine.py
      test_language_filter.py
      test_export.py
      test_config_store.py
      test_e2e_regression.py       # 用真实 xlsm 回归
      fixtures/
        raw_comments.json          # 从「寻找伤心松鼠」原始留言导出的输入
        expected_players.json      # 该活动 Eastblue 玩家信息（打桩）
  frontend/
    index.html                     # 五步向导单页
  启动.command                     # Mac 一键启动
  docs/
```

---

## Task 0: 项目脚手架

**Files:**
- Create: `backend/reward_hub/__init__.py`
- Create: `backend/reward_hub/common.py`
- Create: `backend/requirements.txt`
- Create: `backend/tests/__init__.py`

- [ ] **Step 1: 建包与依赖清单**

`backend/reward_hub/__init__.py`：空文件。
`backend/tests/__init__.py`：空文件。

`backend/requirements.txt`：
```
openpyxl>=3.0
playwright>=1.40
pytest>=7.0
```

- [ ] **Step 2: 写 common.py（数据目录 + JSON 读写 + 子脚本 IO）**

`backend/reward_hub/common.py`：
```python
# -*- coding: utf-8 -*-
"""公共工具：数据目录、JSON 读写、子脚本 emit/log。"""
import os, sys, json


def app_data_dir():
    d = os.path.expanduser("~/.reward_hub_app")
    os.makedirs(d, exist_ok=True)
    return d


def work_dir():
    d = os.path.expanduser("~/Documents/发奖中台工作区")
    os.makedirs(d, exist_ok=True)
    return d


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def emit(obj):
    """子脚本向 server 回一行 JSON。"""
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()


def log(tag, msg):
    print("[%s] %s" % (tag, msg), flush=True)
```

- [ ] **Step 3: 验证包可导入**

Run: `cd backend && python3 -c "from reward_hub import common; print(common.app_data_dir())"`
Expected: 打印 `~/.reward_hub_app` 的绝对路径，无报错。

- [ ] **Step 4: Commit**

```bash
cd "/Users/naihuanjing/Claude/Projects/社群互动发奖中台"
git init 2>/dev/null; git add -A
git commit -m "chore: 发奖中台项目脚手架（包结构+common+依赖）"
```

---

## Task 1: 玩家 ID 提取

**Files:**
- Create: `backend/reward_hub/extract_id.py`
- Test: `backend/tests/test_extract_id.py`

规则：与 VBA `GetID` 完全一致——`(?:^|\D)(1\d{9})(?!\d)`，1 开头 10 位，前后都不是数字（避免 11 位数字如 `21065202703` 误判）。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_extract_id.py`：
```python
from reward_hub.extract_id import extract_id


def test_plain_id():
    assert extract_id("1052837435 Row 3, Column 1") == "1052837435"


def test_id_after_colon():
    assert extract_id("ID: 1093454463 name") == "1093454463"


def test_id_at_line_start():
    assert extract_id("1050551037 + row 3") == "1050551037"


def test_reject_11_digits():
    # 11 位数字不应被当作 10 位 ID 的一部分
    assert extract_id("21065202703 something") is None


def test_no_id():
    assert extract_id("hello world no digits") is None


def test_id_not_starting_with_1():
    assert extract_id("2050551037 abc") is None


def test_first_match_only():
    assert extract_id("1052837435 and 1093454463") == "1052837435"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python3 -m pytest tests/test_extract_id.py -v`
Expected: FAIL，`ModuleNotFoundError` 或 `ImportError: cannot import name 'extract_id'`。

- [ ] **Step 3: 写实现**

`backend/reward_hub/extract_id.py`：
```python
# -*- coding: utf-8 -*-
"""玩家 ID 提取：与原 VBA GetID 同款正则。"""
import re

_PATTERN = re.compile(r"(?:^|\D)(1\d{9})(?!\d)")


def extract_id(text):
    """从留言文本提取第一个合规玩家 ID（1 开头 10 位），无则返回 None。"""
    if text is None:
        return None
    m = _PATTERN.search(str(text))
    return m.group(1) if m else None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python3 -m pytest tests/test_extract_id.py -v`
Expected: 7 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/reward_hub/extract_id.py backend/tests/test_extract_id.py
git commit -m "feat: 玩家 ID 提取（VBA 正则同款）+ 单测"
```

---

## Task 2: 去重

**Files:**
- Create: `backend/reward_hub/dedup.py`
- Test: `backend/tests/test_dedup.py`

一条留言用 dict 表示，字段：`player_id`（str）、`order`（int 留言顺序）、`time`（str）、`likes`（int 点赞）、`replies`（int 回复数）、`content`（str）。三种策略：`earliest`（默认，order 最小的一条）、`all`（不去重）、`best_likes`（点赞最高的一条，并列取 order 最小）。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_dedup.py`：
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python3 -m pytest tests/test_dedup.py -v`
Expected: FAIL，`cannot import name 'dedup'`。

- [ ] **Step 3: 写实现**

`backend/reward_hub/dedup.py`：
```python
# -*- coding: utf-8 -*-
"""按玩家去重：earliest / all / best_likes。输出按 order 升序。"""


def dedup(rows, strategy="earliest"):
    if strategy == "all":
        return sorted(rows, key=lambda r: r["order"])

    best = {}
    for r in rows:
        pid = r["player_id"]
        cur = best.get(pid)
        if cur is None:
            best[pid] = r
        elif strategy == "earliest":
            if r["order"] < cur["order"]:
                best[pid] = r
        elif strategy == "best_likes":
            if r["likes"] > cur["likes"] or (
                r["likes"] == cur["likes"] and r["order"] < cur["order"]):
                best[pid] = r
        else:
            raise ValueError("未知去重策略: %s" % strategy)
    return sorted(best.values(), key=lambda r: r["order"])
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python3 -m pytest tests/test_dedup.py -v`
Expected: 5 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/reward_hub/dedup.py backend/tests/test_dedup.py
git commit -m "feat: 留言去重（最早/全部/最优点赞）+ 单测"
```

---

## Task 3: 语言筛选

**Files:**
- Create: `backend/reward_hub/language_filter.py`
- Test: `backend/tests/test_language_filter.py`

输入：玩家名单（每条含 `lang` 字段）+ 目标语言集合。输出 `(passed, rejected)`，rejected 每条带 `reject_reason="语言不符"`。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_language_filter.py`：
```python
from reward_hub.language_filter import filter_by_language


def _p(pid, lang):
    return {"player_id": pid, "lang": lang}


def test_keeps_target_langs():
    rows = [_p("1", "en"), _p("2", "de"), _p("3", "en")]
    passed, rejected = filter_by_language(rows, {"en"})
    assert [r["player_id"] for r in passed] == ["1", "3"]
    assert [r["player_id"] for r in rejected] == ["2"]


def test_rejected_have_reason():
    _, rejected = filter_by_language([_p("2", "de")], {"en"})
    assert rejected[0]["reject_reason"] == "语言不符"


def test_multi_target_langs():
    rows = [_p("1", "en"), _p("2", "fr"), _p("3", "de")]
    passed, _ = filter_by_language(rows, {"en", "fr"})
    assert {r["player_id"] for r in passed} == {"1", "2"}


def test_case_insensitive():
    passed, _ = filter_by_language([_p("1", "EN")], {"en"})
    assert len(passed) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python3 -m pytest tests/test_language_filter.py -v`
Expected: FAIL，`cannot import name 'filter_by_language'`。

- [ ] **Step 3: 写实现**

`backend/reward_hub/language_filter.py`：
```python
# -*- coding: utf-8 -*-
"""按语言筛选：命中目标语言的进 passed，其余进 rejected（带原因）。"""


def filter_by_language(rows, target_langs):
    targets = {t.lower() for t in target_langs}
    passed, rejected = [], []
    for r in rows:
        if str(r.get("lang", "")).lower() in targets:
            passed.append(r)
        else:
            rr = dict(r)
            rr["reject_reason"] = "语言不符"
            rejected.append(rr)
    return passed, rejected
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python3 -m pytest tests/test_language_filter.py -v`
Expected: 4 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/reward_hub/language_filter.py backend/tests/test_language_filter.py
git commit -m "feat: 语言筛选（目标语言 passed / 其余 rejected）+ 单测"
```

---

## Task 4: 发奖规则引擎

**Files:**
- Create: `backend/reward_hub/rule_engine.py`
- Test: `backend/tests/test_rule_engine.py`

四种规则纯函数，输入 `rows` + `n`，输出中奖子集：
- `top_floors`：按 order 升序取前 n
- `top_likes`：按 likes 降序取前 n，并列 order 小者先
- `top_replies`：按 replies 降序取前 n，并列 order 小者先
- `random_pick`：给定 seed 打乱取 n（用 `random.Random(seed)` 保证可复现）

外加 `run_awards(rows, awards)`：按顺序结算多个奖项，已中奖玩家从后续池剔除；返回 `{award_name: [winners]}` 和 `remaining`。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_rule_engine.py`：
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python3 -m pytest tests/test_rule_engine.py -v`
Expected: FAIL，`cannot import name` 相关。

- [ ] **Step 3: 写实现**

`backend/reward_hub/rule_engine.py`：
```python
# -*- coding: utf-8 -*-
"""发奖规则引擎：四种选取规则 + 多奖项按序结算（不重复中奖）。"""
import random


def top_floors(rows, n):
    return sorted(rows, key=lambda r: r["order"])[:n]


def top_likes(rows, n):
    return sorted(rows, key=lambda r: (-r["likes"], r["order"]))[:n]


def top_replies(rows, n):
    return sorted(rows, key=lambda r: (-r["replies"], r["order"]))[:n]


def random_pick(rows, n, seed=0):
    pool = sorted(rows, key=lambda r: r["order"])  # 先定序，保证 seed 可复现
    rnd = random.Random(seed)
    rnd.shuffle(pool)
    return pool[:n]


_RULES = {
    "top_floors": lambda rows, a: top_floors(rows, a["n"]),
    "top_likes": lambda rows, a: top_likes(rows, a["n"]),
    "top_replies": lambda rows, a: top_replies(rows, a["n"]),
    "random_pick": lambda rows, a: random_pick(rows, a["n"], a.get("seed", 0)),
}


def run_awards(rows, awards):
    """按顺序结算奖项，已中奖玩家从后续池剔除。
    返回 (result: {award_name: [winners]}, remaining: [未中奖])。"""
    pool = list(rows)
    result = {}
    for a in awards:
        rule = _RULES.get(a["rule"])
        if rule is None:
            raise ValueError("未知规则: %s" % a["rule"])
        winners = rule(pool, a)
        result[a["name"]] = winners
        won_ids = {w["player_id"] for w in winners}
        pool = [r for r in pool if r["player_id"] not in won_ids]
    return result, pool
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python3 -m pytest tests/test_rule_engine.py -v`
Expected: 9 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/reward_hub/rule_engine.py backend/tests/test_rule_engine.py
git commit -m "feat: 发奖规则引擎（前N楼/点赞/回复/随机+多奖项排除）+ 单测"
```

---

## Task 5: 多 sheet 导出

**Files:**
- Create: `backend/reward_hub/export.py`
- Test: `backend/tests/test_export.py`

导出一个 xlsx：每个特殊奖一个 sheet + 「参与奖」sheet + 「无效」sheet。玩家列固定顺序（与现有 xlsm 一致）：留言顺序、留言时间、玩家ID、语言、别墅等级、角色名称、角色等级、角色创建时间、服务器、历史充值总额、最后登录时间。无效 sheet 额外末列「原因」。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_export.py`：
```python
import openpyxl
from reward_hub.export import export_reward_workbook

PLAYER_COLS = ["留言顺序", "留言时间", "玩家ID", "语言", "别墅等级",
               "角色名称", "角色等级", "角色创建时间", "服务器",
               "历史充值总额", "最后登录时间"]


def _p(pid, order, lang="en"):
    return {"order": order, "time": "2026-06-26 08:00:00", "player_id": pid,
            "lang": lang, "villa": "37", "role_name": "Hero", "role_level": "55",
            "role_created": "2019-05-02", "server": "S177",
            "total_recharge": "100", "last_login": "2026-07-03"}


def test_creates_sheets(tmp_path):
    out = tmp_path / "out.xlsx"
    awards = {"先锋奖": [_p("1000000001", 1)]}
    participation = [_p("1000000002", 2)]
    invalid = [{"player_id": "", "content": "no id", "reject_reason": "无有效ID"}]
    export_reward_workbook(str(out), awards, participation, invalid)

    wb = openpyxl.load_workbook(str(out))
    assert wb.sheetnames == ["先锋奖", "参与奖", "无效"]


def test_award_sheet_header_and_row(tmp_path):
    out = tmp_path / "out.xlsx"
    export_reward_workbook(str(out), {"先锋奖": [_p("1000000001", 1)]}, [], [])
    wb = openpyxl.load_workbook(str(out))
    ws = wb["先锋奖"]
    assert [c.value for c in ws[1]] == PLAYER_COLS
    assert ws.cell(row=2, column=3).value == "1000000001"  # 玩家ID 列


def test_invalid_sheet_has_reason_column(tmp_path):
    out = tmp_path / "out.xlsx"
    invalid = [{"player_id": "", "content": "hi", "reject_reason": "无有效ID"}]
    export_reward_workbook(str(out), {}, [], invalid)
    wb = openpyxl.load_workbook(str(out))
    ws = wb["无效"]
    header = [c.value for c in ws[1]]
    assert "原因" in header
    assert ws.cell(row=2, column=header.index("原因") + 1).value == "无有效ID"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python3 -m pytest tests/test_export.py -v`
Expected: FAIL，`cannot import name 'export_reward_workbook'`。

- [ ] **Step 3: 写实现**

`backend/reward_hub/export.py`：
```python
# -*- coding: utf-8 -*-
"""导出发奖名单为多 sheet xlsx。"""
import openpyxl

PLAYER_COLS = ["留言顺序", "留言时间", "玩家ID", "语言", "别墅等级",
               "角色名称", "角色等级", "角色创建时间", "服务器",
               "历史充值总额", "最后登录时间"]
# 玩家 dict 字段 → 中文列
_FIELD = ["order", "time", "player_id", "lang", "villa", "role_name",
          "role_level", "role_created", "server", "total_recharge", "last_login"]


def _write_player_sheet(ws, rows):
    ws.append(PLAYER_COLS)
    for r in rows:
        ws.append([r.get(f, "") for f in _FIELD])


def _write_invalid_sheet(ws, rows):
    header = ["玩家ID", "留言内容", "原因"]
    ws.append(header)
    for r in rows:
        ws.append([r.get("player_id", ""), r.get("content", ""),
                   r.get("reject_reason", "")])


def export_reward_workbook(path, awards, participation, invalid):
    """awards: {奖项名: [玩家]}；participation: [玩家]；invalid: [无效记录]。"""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, winners in awards.items():
        _write_player_sheet(wb.create_sheet(title=name[:31]), winners)
    _write_player_sheet(wb.create_sheet(title="参与奖"), participation)
    _write_invalid_sheet(wb.create_sheet(title="无效"), invalid)
    wb.save(path)
    return path
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python3 -m pytest tests/test_export.py -v`
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/reward_hub/export.py backend/tests/test_export.py
git commit -m "feat: 多 sheet xlsx 导出（特殊奖/参与奖/无效）+ 单测"
```

---

## Task 6: 配置持久化（预设）

**Files:**
- Create: `backend/reward_hub/config_store.py`
- Test: `backend/tests/test_config_store.py`

存 `~/.reward_hub_app/presets.json`：`{"default": "<预设名>", "presets": {"<名>": {...配置...}}}`。配置含：`dedup_strategy`、`eastblue`（game_id/game_langs/except_internal/search_num/last_act_time/server_ids）、`target_langs`。**不含**发奖规则。API：`save_preset(name, config)`、`load_preset(name)`、`list_presets()`、`set_default(name)`、`get_default()`。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_config_store.py`：
```python
import reward_hub.config_store as cs


def _store(tmp_path):
    return cs.ConfigStore(str(tmp_path / "presets.json"))


def test_save_and_load(tmp_path):
    store = _store(tmp_path)
    store.save_preset("先锋活动", {"dedup_strategy": "earliest",
                                    "target_langs": ["en"]})
    got = store.load_preset("先锋活动")
    assert got["dedup_strategy"] == "earliest"
    assert got["target_langs"] == ["en"]


def test_list_presets(tmp_path):
    store = _store(tmp_path)
    store.save_preset("A", {"target_langs": ["en"]})
    store.save_preset("B", {"target_langs": ["de"]})
    assert set(store.list_presets()) == {"A", "B"}


def test_set_and_get_default(tmp_path):
    store = _store(tmp_path)
    store.save_preset("A", {"target_langs": ["en"]})
    store.set_default("A")
    assert store.get_default() == "A"


def test_persists_across_instances(tmp_path):
    p = str(tmp_path / "presets.json")
    cs.ConfigStore(p).save_preset("A", {"target_langs": ["en"]})
    assert "A" in cs.ConfigStore(p).list_presets()


def test_load_missing_returns_none(tmp_path):
    assert _store(tmp_path).load_preset("nope") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python3 -m pytest tests/test_config_store.py -v`
Expected: FAIL，`AttributeError: module ... has no attribute 'ConfigStore'`。

- [ ] **Step 3: 写实现**

`backend/reward_hub/config_store.py`：
```python
# -*- coding: utf-8 -*-
"""配置预设持久化（不含发奖规则）。"""
from reward_hub.common import load_json, save_json


class ConfigStore:
    def __init__(self, path):
        self.path = path

    def _data(self):
        return load_json(self.path, {"default": None, "presets": {}})

    def save_preset(self, name, config):
        d = self._data()
        d["presets"][name] = config
        save_json(self.path, d)

    def load_preset(self, name):
        return self._data()["presets"].get(name)

    def list_presets(self):
        return list(self._data()["presets"].keys())

    def set_default(self, name):
        d = self._data()
        d["default"] = name
        save_json(self.path, d)

    def get_default(self):
        return self._data()["default"]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python3 -m pytest tests/test_config_store.py -v`
Expected: 5 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/reward_hub/config_store.py backend/tests/test_config_store.py
git commit -m "feat: 配置预设持久化（去重/eastblue/语言，多预设+默认）+ 单测"
```

---

## Task 7: 端到端回归（真实 xlsm）

**Files:**
- Create: `backend/tests/fixtures/build_fixtures.py`（一次性从 xlsm 生成 fixture）
- Create: `backend/tests/fixtures/raw_comments.json`
- Create: `backend/tests/fixtures/expected_players.json`
- Create: `backend/tests/test_e2e_regression.py`

目标：用「寻找伤心松鼠」xlsm 的「原始留言」sheet 当输入，跑「提取 ID → 去重 → 匹配玩家信息（用 xlsm 里已有的玩家信息打桩）→ 语言筛选 → 前 100 楼(先锋奖) + 其余(参与奖)」，输出应与 xlsm 里的「先锋奖」「参与奖」两个 sheet 的玩家 ID 集合一致。

- [ ] **Step 1: 写 fixture 生成脚本并运行**

`backend/tests/fixtures/build_fixtures.py`：
```python
# -*- coding: utf-8 -*-
"""从「寻找伤心松鼠」xlsm 抽取回归 fixture（一次性运行，产物提交仓库）。"""
import json, os
import openpyxl

XLSM = os.path.expanduser(
    "~/Library/Containers/com.xunmeng.knock/5azlYjzeJT0A/files/寻找伤心松鼠社群互动发奖.xlsm")
HERE = os.path.dirname(os.path.abspath(__file__))

wb = openpyxl.load_workbook(XLSM, read_only=True, data_only=True)

# 原始留言 → raw_comments.json（序号/留言内容/按赞数/留言时间）
raw = []
ws = wb["原始留言"]
for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
    seq, name, content, likes, ctime, _ = row
    if seq is None:
        continue
    raw.append({"order": int(seq), "content": content or "",
                "likes": int(likes) if isinstance(likes, (int, float)) else 0,
                "replies": 0, "time": str(ctime) if ctime else ""})
json.dump(raw, open(os.path.join(HERE, "raw_comments.json"), "w"),
          ensure_ascii=False, indent=2)

# ID提取 sheet → expected_players.json（玩家ID → 玩家信息）打桩 Eastblue
players = {}
ws = wb["ID提取"]
for row in ws.iter_rows(min_row=2, values_only=True):
    pid = row[5]
    if not pid:
        continue
    players[str(pid)] = {
        "player_id": str(pid), "lang": row[6], "villa": row[7],
        "role_name": row[8], "role_level": row[9], "role_created": str(row[10]),
        "server": row[11], "total_recharge": row[12], "last_login": str(row[13])}
json.dump(players, open(os.path.join(HERE, "expected_players.json"), "w"),
          ensure_ascii=False, indent=2)

# 先锋奖/参与奖玩家ID集合（期望结果）
for sheet, fn in [("先锋奖", "expected_vanguard.json"),
                  ("参与奖", "expected_participation.json")]:
    ids = []
    ws = wb[sheet]
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[5]:
            ids.append(str(row[5]))
    json.dump(ids, open(os.path.join(HERE, fn), "w"), ensure_ascii=False, indent=2)

print("fixtures 生成完成")
```

Run: `cd backend && python3 tests/fixtures/build_fixtures.py`
Expected: 打印「fixtures 生成完成」，生成 `raw_comments.json`、`expected_players.json`、`expected_vanguard.json`、`expected_participation.json`。

⚠️ 若 xlsm 里先锋奖/参与奖的划分口径与「前100楼」不完全一致（例如手工剔过刷楼或含非 en），Step 3 的断言用**集合 + 数量**做，并在测试里打印差异，交由人工确认口径后再定稿 assert（见 executing-plans 的检查点）。

- [ ] **Step 2: 写回归测试**

`backend/tests/test_e2e_regression.py`：
```python
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
```

- [ ] **Step 3: 跑回归测试**

Run: `cd backend && python3 -m pytest tests/test_e2e_regression.py -v -s`
Expected: PASS。若 FAIL，打印的「缺失/多出」用于和石上核对手工口径（可能手工剔了刷楼/非 en），据此调整 fixture 口径或去重/筛选参数，**不要**为了过测试而改规则逻辑。

- [ ] **Step 4: Commit**

```bash
git add backend/tests/fixtures backend/tests/test_e2e_regression.py
git commit -m "test: 用真实 xlsm 做发奖流程端到端回归"
```

---

## Task 8: 本地服务 server.py（串起 Phase 1）

**Files:**
- Create: `backend/server.py`
- Create: `frontend/index.html`（先放最小骨架，Task 10 做完整向导）
- Create: `启动.command`

服务用标准库 `ThreadingHTTPServer`，端口 8765。路由：
- `GET /` → 返回 `frontend/index.html`
- `GET /api/ping` → `{"ok": true}`
- `GET /api/presets` → 列预设 + 默认
- `POST /api/presets` → 保存预设 `{name, config}`
- `POST /api/process` → 入参 `{raw_comments, players, dedup_strategy, target_langs, awards}`，跑完整 Phase 1 流程，返回各 sheet 数据供前端预览
- `POST /api/export` → 入参各 sheet 数据，写 xlsx 到工作区，返回文件路径

- [ ] **Step 1: 写 server.py**

`backend/server.py`：
```python
# -*- coding: utf-8 -*-
"""发奖中台本地服务（标准库 http.server，无框架）。"""
import os, sys, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from reward_hub import common
from reward_hub.extract_id import extract_id
from reward_hub.dedup import dedup
from reward_hub.language_filter import filter_by_language
from reward_hub.rule_engine import run_awards
from reward_hub.export import export_reward_workbook
from reward_hub.config_store import ConfigStore

ROOT = os.path.dirname(HERE)
FRONTEND = os.path.join(ROOT, "frontend")
PRESETS = os.path.join(common.app_data_dir(), "presets.json")
PORT = 8765


def process_pipeline(raw_comments, players, dedup_strategy, target_langs, awards):
    """完整 Phase 1 流程：提取→去重→匹配→语言筛选→发奖。返回可预览的各 sheet。"""
    invalid = []
    rows = []
    for c in raw_comments:
        pid = extract_id(c.get("content", ""))
        if pid:
            rows.append({**c, "player_id": pid})
        else:
            invalid.append({**c, "reject_reason": "无有效ID"})

    rows = dedup(rows, dedup_strategy)

    matched = []
    for r in rows:
        info = players.get(r["player_id"])
        if info:
            matched.append({**r, **info})
        else:
            invalid.append({**r, "reject_reason": "Eastblue无记录"})

    passed, lang_rejected = filter_by_language(matched, set(target_langs))
    invalid.extend(lang_rejected)

    result, remaining = run_awards(passed, awards)
    return {"awards": result, "participation": remaining, "invalid": invalid}


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            with open(os.path.join(FRONTEND, "index.html"), "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/api/ping":
            self._json({"ok": True})
        elif self.path == "/api/presets":
            store = ConfigStore(PRESETS)
            self._json({"default": store.get_default(),
                        "presets": {n: store.load_preset(n) for n in store.list_presets()}})
        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        try:
            if self.path == "/api/presets":
                b = self._body()
                store = ConfigStore(PRESETS)
                store.save_preset(b["name"], b["config"])
                if b.get("as_default"):
                    store.set_default(b["name"])
                self._json({"ok": True})
            elif self.path == "/api/process":
                b = self._body()
                out = process_pipeline(
                    b["raw_comments"], b.get("players", {}),
                    b.get("dedup_strategy", "earliest"),
                    b.get("target_langs", ["en"]), b.get("awards", []))
                self._json({"ok": True, **out})
            elif self.path == "/api/export":
                b = self._body()
                out_path = os.path.join(common.work_dir(), b.get("filename", "发奖名单.xlsx"))
                export_reward_workbook(out_path, b["awards"], b["participation"], b["invalid"])
                self._json({"ok": True, "path": out_path})
            else:
                self._json({"ok": False, "error": "not found"}, 404)
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)


if __name__ == "__main__":
    print("发奖中台已启动：http://127.0.0.1:%d" % PORT, flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
```

- [ ] **Step 2: 写最小前端骨架**

`frontend/index.html`：
```html
<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>社群互动发奖中台</title></head>
<body><h1>社群互动发奖中台</h1><p id="status">连接中…</p>
<script>
fetch("/api/ping").then(r=>r.json()).then(d=>{
  document.getElementById("status").textContent = d.ok ? "服务已就绪" : "异常";
});
</script></body></html>
```

- [ ] **Step 3: 写启动脚本**

`启动.command`：
```bash
#!/bin/bash
# 社群互动发奖中台 — 一键启动（Mac）。双击即可运行。
cd "$(dirname "$0")/backend" || exit 1
echo "正在启动 社群互动发奖中台…"
echo "（首次运行会自动安装依赖：openpyxl / playwright + 浏览器内核，可能需要几分钟）"
python3 -c "import openpyxl" 2>/dev/null || pip3 install -r requirements.txt
python3 server.py &
SERVER_PID=$!
trap "kill $SERVER_PID 2>/dev/null" EXIT
for i in $(seq 1 150); do
  if curl -s -m 2 http://127.0.0.1:8765/api/ping >/dev/null 2>&1; then break; fi
  sleep 2
done
open "http://127.0.0.1:8765"
echo "已在浏览器打开。关闭此窗口或按 Ctrl+C 可停止服务。"
wait $SERVER_PID
```

Run: `chmod +x "/Users/naihuanjing/Claude/Projects/社群互动发奖中台/启动.command"`

- [ ] **Step 4: 手动冒烟测试**

Run: `cd backend && python3 server.py &` 然后 `curl -s http://127.0.0.1:8765/api/ping`
Expected: `{"ok": true}`。再 `curl -s -X POST http://127.0.0.1:8765/api/process -d '{"raw_comments":[{"order":1,"content":"1052837435 hi","likes":0,"replies":0,"time":""}],"players":{"1052837435":{"player_id":"1052837435","lang":"en","villa":"37","role_name":"K","role_level":"55","role_created":"2019","server":"S177","total_recharge":"100","last_login":"2026"}},"target_langs":["en"],"awards":[{"name":"先锋奖","rule":"top_floors","n":1}]}'`
Expected: 返回含 `"先锋奖"` 且该玩家在内。跑完 `kill %1`。

- [ ] **Step 5: Commit**

```bash
git add backend/server.py frontend/index.html 启动.command
git commit -m "feat: 本地服务串起 Phase1 流程 + 一键启动脚本"
```

---

## Task 9: Eastblue 自动下载（Phase 2）

**Files:**
- Create: `backend/reward_hub/eastblue_download.py`
- Create: `backend/reward_hub/eastblue_parse.py`
- Test: `backend/tests/test_eastblue_parse.py`
- Modify: `backend/server.py`（加 `/api/eastblue` 路由）

`eastblue_download.py` 用 Playwright 持久化 profile（`~/.reward_hub_app/eastblue_profile`）打开中台拼好的下载链接，监听 `page.on("download")` 捕获 xlsx 存到工作区；首次未登录则停在 SSO 页等人工登录（headless=False），登录态持久化后续免登。参考 `Projects/Locoflow本地工具/backend/locoflow_tool/download_locoflow.py` 的 download 捕获写法。emit `{ok, path}`。

`eastblue_parse.py`：读下载的 xlsx，识别表头，返回 `{player_id: {玩家信息字段}}`，供 process_pipeline 的 `players` 用。**这是能单测的部分**，先做。

- [ ] **Step 1: 写 parse 失败测试**

`backend/tests/test_eastblue_parse.py`：
```python
import openpyxl
from reward_hub.eastblue_parse import parse_players


def _make_xlsx(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["玩家ID", "语言", "别墅等级", "角色名称", "角色等级",
               "角色创建时间", "服务器", "历史充值总额", "最后登录时间"])
    ws.append(["1052837435", "en", "37", "Kraken", "55",
               "2019-05-02", "S177", "87024.93", "2026-07-03"])
    p = tmp_path / "eb.xlsx"
    wb.save(str(p))
    return str(p)


def test_parse_returns_dict_keyed_by_id(tmp_path):
    players = parse_players(_make_xlsx(tmp_path))
    assert "1052837435" in players
    assert players["1052837435"]["lang"] == "en"
    assert players["1052837435"]["server"] == "S177"


def test_parse_maps_all_fields(tmp_path):
    players = parse_players(_make_xlsx(tmp_path))
    p = players["1052837435"]
    for k in ["lang", "villa", "role_name", "role_level",
              "role_created", "server", "total_recharge", "last_login"]:
        assert k in p
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python3 -m pytest tests/test_eastblue_parse.py -v`
Expected: FAIL，`cannot import name 'parse_players'`。

- [ ] **Step 3: 写 parse 实现**

`backend/reward_hub/eastblue_parse.py`：
```python
# -*- coding: utf-8 -*-
"""解析 Eastblue 导出 xlsx → {player_id: 玩家信息}。"""
import openpyxl

# Eastblue 表头中文 → 内部字段（表头以实测为准，命名有出入在此调整）
_HEADER_MAP = {
    "玩家ID": "player_id", "语言": "lang", "别墅等级": "villa",
    "角色名称": "role_name", "角色等级": "role_level",
    "角色创建时间": "role_created", "服务器": "server",
    "历史充值总额": "total_recharge", "最后登录时间": "last_login",
}


def parse_players(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header = [str(h) if h is not None else "" for h in next(rows)]
    idx = {i: _HEADER_MAP[h] for i, h in enumerate(header) if h in _HEADER_MAP}
    players = {}
    for row in rows:
        rec = {}
        for i, field in idx.items():
            rec[field] = row[i] if i < len(row) else ""
        pid = rec.get("player_id")
        if pid:
            rec["player_id"] = str(pid)
            players[str(pid)] = rec
    return players
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python3 -m pytest tests/test_eastblue_parse.py -v`
Expected: 2 passed。

- [ ] **Step 5: 写 download 脚本（Playwright，无单测，手动实测）**

`backend/reward_hub/eastblue_download.py`：
```python
# -*- coding: utf-8 -*-
"""用 Playwright 打开 Eastblue 下载链接，捕获自动下载的 xlsx。
用法: python3 eastblue_download.py --url "<下载链接>" --outdir <目录>
emit 一行 JSON: {ok, path} 或 {ok:false, error}
链接是网页地址(#/ 前端路由 + auto_download=1)，前端 JS 触发下载。
首次未登录会停在 SSO 页(headless=False)，人工登录后 profile 持久化免登。
"""
import os, sys, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
try:
    from reward_hub.common import emit, app_data_dir, work_dir
except ImportError:
    sys.path.insert(0, os.path.dirname(HERE))
    from reward_hub.common import emit, app_data_dir, work_dir


def download(url, outdir):
    from playwright.sync_api import sync_playwright
    profile = os.path.join(app_data_dir(), "eastblue_profile")
    os.makedirs(profile, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile, headless=False, accept_downloads=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            with page.expect_download(timeout=120000) as dl_info:
                page.goto(url)
                # 若停在登录页，人工登录后前端会自动重定向并触发下载
            dl = dl_info.value
            fname = dl.suggested_filename or "eastblue_players.xlsx"
            path = os.path.join(outdir, fname)
            dl.save_as(path)
            emit({"ok": True, "path": path})
        except Exception as e:
            emit({"ok": False, "error": str(e)})
        finally:
            ctx.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--outdir", default=work_dir())
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    download(a.url, a.outdir)
```

- [ ] **Step 6: 加 server 路由 + 手动实测**

在 `backend/server.py` 的 `do_POST` 里，`/api/export` 分支后加：
```python
            elif self.path == "/api/eastblue":
                b = self._body()
                import subprocess
                script = os.path.join(HERE, "reward_hub", "eastblue_download.py")
                proc = subprocess.run(
                    [sys.executable, script, "--url", b["url"],
                     "--outdir", common.work_dir()],
                    capture_output=True, text=True, timeout=180)
                line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else "{}"
                res = json.loads(line)
                if res.get("ok"):
                    from reward_hub.eastblue_parse import parse_players
                    res["players"] = parse_players(res["path"])
                self._json(res)
```

手动实测：确保已 `python3 -m playwright install chromium`，用真实链接
`https://eastblue.xinyoudi.com/home/#/player-management?game_id=97&attribute_langs=en&game_langs=en,fr,de,ja,ru,ko,es,tr,ar,it,pt,th&except_internal=1&search_num=1000&last_act_time=last_three_year&auto_download=1`
跑 `python3 reward_hub/eastblue_download.py --url "<上面链接>"`。
Expected: 弹出浏览器（首次需人工登 SSO），下载 xlsx，emit `{"ok": true, "path": "..."}`。**若表头与 `_HEADER_MAP` 不符，据实测表头修正 map。**

- [ ] **Step 7: Commit**

```bash
git add backend/reward_hub/eastblue_download.py backend/reward_hub/eastblue_parse.py backend/tests/test_eastblue_parse.py backend/server.py
git commit -m "feat: Eastblue 自动下载(Playwright)+解析玩家信息(单测)"
```

---

## Task 10: 前端五步向导

**Files:**
- Modify: `frontend/index.html`（替换骨架为完整向导）

用 frontend-design 技能的审美标准做一个美观、清晰的单页向导（这是石上明确要求的）。五步：抓留言（Phase 3 前先支持 CSV/Excel 导入 + 手工贴）、清洗提取 ID（表格预览绿/红）、拉玩家信息（配置表单 + 「自动下载」按钮调 `/api/eastblue`）、语言筛选（多选）、发奖规则 + 导出（奖项列表可增删 + 各 sheet 预览 + 导出按钮调 `/api/export`）。配置区顶部有预设下拉（读/存 `/api/presets`）。

- [ ] **Step 1: 调用 frontend-design 技能产出向导页面**

按 spec 的五步向导与配置持久化实现 `frontend/index.html`：
- 顶部：预设选择/保存/设默认（GET/POST `/api/presets`）
- 步骤条 + 每步可回退
- 步骤 1：文件导入（前端用 SheetJS 或让后端解析）/ 文本粘贴，解析成 `raw_comments`
- 步骤 2：调 `/api/process`（此时 awards 空、players 空）预览提取结果，绿=有ID 红=无ID
- 步骤 3：Eastblue 配置表单 → 「自动下载」调 `/api/eastblue` 拿 `players`
- 步骤 4：语言多选，写入 `target_langs`
- 步骤 5：奖项增删（名称/规则下拉/人数/随机种子）→ 调 `/api/process` 拿最终分组 → 各 sheet 表格预览 → 「导出」调 `/api/export`
- 全流程 state 存前端内存 + 关键配置可存预设

- [ ] **Step 2: 用 preview 工具验证**

用 preview_start 起服务、preview_snapshot/preview_screenshot 核对每步渲染与交互（导入→预览→筛选→出名单→导出），控制台无报错。

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat: 五步向导前端（美观单页+预设+各sheet预览）"
```

---

## Task 11: FB 留言抓取整合（Phase 3）

**Files:**
- Modify: `frontend/index.html`（步骤 1 内嵌 FB 抓取）

把 `Projects/Facebook留言抓取/index.html` 的 Graph API 抓取逻辑（App ID / Token 两种登录、选粉专、选帖子、抓留言+回复含点赞/回复数）整合进步骤 1，抓完直接转成 `raw_comments`（字段对齐：order=留言顺序、content=留言内容、likes=按赞数、replies=回复数、time=留言时间）进入步骤 2。保留 CSV/Excel 导入兜底。

- [ ] **Step 1: 移植 FB 抓取逻辑**

读 `Projects/Facebook留言抓取/index.html`，把其 FB.init/登录/`/me/accounts`/帖子留言分页抓取/回复抓取逻辑搬进步骤 1，产物映射为 `raw_comments`。

- [ ] **Step 2: 手动实测**

用真实 App ID / Token（石上提供）抓一个自家粉专帖子，确认留言+回复都抓到、字段映射正确、能顺畅进入步骤 2。

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat: 整合 FB 留言抓取到步骤1（含回复+点赞/回复数）"
```

---

## Task 12: 全量测试 + 收尾

- [ ] **Step 1: 跑全部单测**

Run: `cd backend && python3 -m pytest -v`
Expected: 全绿（extract_id / dedup / language_filter / rule_engine / export / config_store / eastblue_parse / e2e_regression）。

- [ ] **Step 2: 完整链路手动走一遍**

启动.command → 导入/抓留言 → 提取 → Eastblue 下载 → 语言筛选 → 配奖项 → 预览 → 导出。核对导出 xlsx 的 sheet 结构与内容正确。

- [ ] **Step 3: 写 README**

`Projects/社群互动发奖中台/README.md`：说明用途、启动方式（双击 启动.command）、五步流程、依赖、Eastblue 首次登录说明、FB App ID 填写说明。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs: README + 全量测试通过"
```

---

## Self-Review 记录

- **Spec 覆盖**：抓留言(T11)、提取ID(T1)、去重(T2/spec 步骤2)、拉玩家(T9)、语言筛选(T3)、规则引擎(T4)、多sheet导出(T5)、配置持久化(T6)、五步向导(T10)、Eastblue Playwright 下载(T9)、回归测试(T7)——全部有对应任务。
- **漏斗顺序**：process_pipeline(T8) 严格按 提取→去重→匹配→语言筛选→发奖，规则只作用于筛选后名单，符合 spec ★。
- **类型一致**：玩家 dict 字段（player_id/order/time/likes/replies/lang/villa/role_name/role_level/role_created/server/total_recharge/last_login）在 T1-T9 全程一致；export 的 `_FIELD` 与之对齐。
- **占位符**：无 TBD；唯一需实测确认的是 Eastblue 真实表头（T9 Step6）与 xlsm 手工口径（T7 Step3），均已写明处理方式。
