# 第五步「留言时间筛选（逾期判定）」设计

日期：2026-07-20
状态：已确认，待实现

## 1. 背景与目标

活动有截止时间。部分玩家在活动时间过后仍来评论——**无论其 ID 或答案是否有效，错过时间窗就不算有效参与（逾期参与）**。

需求：在第五步「结算发奖」新增按**留言/回复时间**的筛选：
- 支持三种模式：某时间**之前** / 某时间**之后** / 某时间**段内**。
- 时间窗之外的留言判为**无效**，原因写明「逾期参与」。
- 该判定是**最高优先级**——高于所有发奖判定，也高于「无有效ID / Eastblue无记录 / 语言不符」等既有淘汰。
- 界面上标注时间基准为 **UTC+0**。

## 2. 时区确认（关键前提）

留言时间来自 Facebook Graph API 的 `created_time`（[frontend/index.html:1116](../../../frontend/index.html)，原样存字符串）。

**Facebook Graph API 的 `created_time` 默认即 UTC+0**，格式形如 `2017-06-06T18:04:10+0000`（末尾 `+0000` = UTC 偏移）。官方文档示例与多方资料一致。

结论：
- 走「Facebook 抓取」拉到的留言时间 **= UTC+0**，(UTC+0) 批注准确。
- ⚠️ 走「手工粘贴」导入时，时间列内容由用户决定；若从 FB 网页界面复制，通常是浏览器本地时区（大概率 UTC+8），**不是** UTC+0。故 (UTC+0) 批注严格只对抓取路径成立，粘贴路径需用户自行保证填的是 UTC+0。界面须提示此点。

## 3. 判定逻辑与优先级

在后端 `process_pipeline`（[backend/server.py:107](../../../backend/server.py)）**最前面**加时间闸门，位于「提取ID」之前。

淘汰顺序（新）：
```
时间闸门(逾期) → 提取ID → 去重 → 匹配Eastblue → 语言筛 → 发奖
```

- 逾期留言直接进 `invalid`，`reject_reason` 以「逾期参与」开头并附边界；不再进入后续任何判定。
- 因此「逾期」天然优先于「无有效ID / 空内容 / Eastblue无记录 / 语言不符」——同一条留言若既逾期又无ID，只标「逾期参与」。
- 关键词奖的「全部留言池」`all_comments` 由通过闸门后的 `valid` 构建，故逾期的正确答案也不计入关键词奖。
- **仅为展示**：对逾期记录尽力 `extract_id`，把 `player_id` 补进记录（便于导出/日志核对），但**不影响判定**（原因仍是「逾期参与」）。

## 4. 后端实现

### 4.1 新模块 `backend/reward_hub/time_filter.py`

仿 `language_filter.py` 风格，纯函数、可单测：

```python
def filter_by_time(rows, cfg):
    """cfg=None 或 cfg['mode'] in (None,'','off') → 全放行 (rows, [], stats)。
    否则按 mode(before/after/between) 分区。
    返回 (passed, rejected, stats)：
      rejected 每条带 reject_reason='逾期参与（活动时间外·...UTC+0）'
      stats = {'overdue': int, 'no_time': int}
    无法解析时间(_parse_utc 返回 None)的留言 → 放行 + stats['no_time'] += 1（宁放过不错杀）。
    """
```

辅助：
- `_parse_utc(s)` → tz-aware UTC datetime 或 None。兼容（Python 3.9）：
  - `...+0000` / `...+00:00` / `...Z`（先归一 `Z`→`+00:00`、无冒号偏移 `+0000`→`+00:00`）
  - 无偏移（视为 UTC）、`YYYY-MM-DD HH:MM:SS`（空格分隔）、纯日期 `YYYY-MM-DD`
  - 归一后用 `datetime.fromisoformat`；naive 结果补 UTC tzinfo；任何异常 → None。
- `_parse_bound(s)` → 解析界面 `datetime-local` 值（`YYYY-MM-DDTHH:MM`，视为 UTC）。

边界口径（**闭区间**）：
- before(end)：`t <= end` 放行；否则「逾期参与（活动时间外·晚于 {end} UTC+0）」
- after(start)：`t >= start` 放行；否则「逾期参与（活动时间外·早于 {start} UTC+0）」
- between(start,end)：`start <= t <= end` 放行；早于 start → 「…早于开始 {start}…」，晚于 end → 「…晚于结束 {end}…」
- 边界展示格式 `YYYY-MM-DD HH:MM`。

### 4.2 接入 `process_pipeline`

签名新增带默认值参数（保证既有调用/测试不破）：
```python
def process_pipeline(raw_comments, players, dedup_strategy, target_langs, awards,
                     allow_winner_participation=False, time_filter=None):
```
流程开头：
```python
in_window, overdue, tf_stats = filter_by_time(raw_comments, time_filter)
for r in overdue:
    pid = extract_id(r.get("content", ""))   # 仅展示用
    if pid: r["player_id"] = pid
invalid.extend(overdue)
# 后续循环遍历 in_window（原为 raw_comments）
```
返回值新增（不改动 awards/participation/invalid 三键，避免破坏其它消费方）：
```python
"overdue_stats": {"mode": <mode or 'off'>, "overdue": N, "no_time": M}
```

### 4.3 结算日志 `write_run_log`

`rec` 增加 `"时间筛选": {模式, 边界, 逾期数, 无时间戳放行数}`，供事后审计。

### 4.4 HTTP 处理器

`/api/process` 分支把 `b.get("time_filter")` 传入 `process_pipeline`，并把该 cfg 一并传给 `write_run_log` 的 inputs。

## 5. 前端实现

### 5.1 面板（Step 5 奖项列表正上方）

「⏱ 时间筛选 · 逾期判定」面板：
- 模式 `<select id="timeFilterMode">`：`关闭（默认）` / `某时间之前` / `某时间之后` / `某时间段内`。
- 按模式动态显示 `<input type="datetime-local">`：
  - 之前 → `#tfEnd`（结束时间，此后视为逾期）
  - 之后 → `#tfStart`（开始时间，此前视为无效）
  - 期间 → `#tfStart` ~ `#tfEnd`
- 小字批注：`时间基准 UTC+0（Facebook 抓取的留言时间即 UTC+0；手工粘贴请确保填的也是 UTC+0）`。

### 5.2 校验（结算前）

- 模式≠关闭但对应时间为空 → 拦截结算，提示「请填写时间，或将模式设为关闭」。
- 期间模式 start > end → 拦截，提示「开始时间不能晚于结束时间」。

### 5.3 payload 与结果摘要

- `payload.time_filter = cfg 或 null`。
- 结算后若 `res.overdue_stats` 存在且模式≠off，结果区顶部显示摘要：
  `时间筛选：{模式中文} · 逾期 N 条 · 无时间戳放行 M 条`（M>0 时才提示无时间戳，呼应「放行+提示条数」）。
- 无效名单表格已有「原因」列，自动显示「逾期参与…」，无需改动。

### 5.4 字体一致（Mac + Windows）

把 `input[type="datetime-local"]`（连带 `date`/`time`）并入既有输入框规则（[frontend/index.html:179](../../../frontend/index.html)），`font-family: var(--mono)`——与第五步其它数字/文本输入框一致：Mac=SF Mono，Windows 经 `html.win` 覆盖成微软雅黑（[frontend/index.html:44](../../../frontend/index.html)）。原生日历弹层由系统绘制无法改（浏览器限制），但输入框内显示值字体统一。

## 6. 测试

### 6.1 单测 `backend/tests/test_time_filter.py`
- `_parse_utc`：`+0000`/`+00:00`/`Z`/无偏移/空格分隔/纯日期/空串/乱码。
- before/after/between：界内、界外、卡边界（闭区间含边界）。
- 无时间戳 → 放行 + `no_time` 计数。
- cfg=None / mode='off' → 全放行、rejected 空。

### 6.2 集成测 `backend/tests/test_overdue_pipeline.py`
- 逾期留言 → invalid「逾期参与…」，且**不**出现在任何奖项/参与奖。
- 逾期优先于「无有效ID」（既逾期又无ID → 原因「逾期参与」）。
- 逾期的关键词正确答案 → 不进关键词奖。
- 无时间戳留言 → 照常参与并可中奖；`overdue_stats.no_time` 计数正确。
- 回归：`test_participation_option.py` 等既有测试全绿。

### 6.3 实机
- 本机跑起（:18765），造含「界内/迟到/太早/无时间」留言，逐模式结算。
- 核对：无效名单显示「逾期参与…」、奖池已排除逾期、摘要条数正确、导出 xlsx「无效」sheet 正确、Step 5 面板美观、日期输入框字体与相邻输入框一致（截图，Mac）。
- Windows：本机无法测，另附验收要点（面板显示、字体、三模式结算）。

## 7. 遗憾 / 局限

1. 手工粘贴路径时区不可控——只能假定 UTC+0，界面提示但无法自动校正（抓取路径无此问题）。
2. FB `created_time` 为发布时间；留言被编辑时 FB 不提供编辑时间，只能按发布时间判逾期。
3. 原生日历弹层字体由系统绘制，无法自定义（输入框显示值已统一）。
4. 边界闭区间、默认分钟精度；卡秒级需另开秒精度。
5. 无时间戳「放行」是"宁放过不错杀"取舍；若需从严须改口径。

## 8. 不做（YAGNI）

- 不支持多时区选择（固定 UTC+0，符合数据源）。
- 时间筛选配置**不**存入预设（与第五步奖项「不存入预设」一致，属活动级临时参数）。
- 不做「按回复层级/楼中楼单独设时间」等更细粒度。
