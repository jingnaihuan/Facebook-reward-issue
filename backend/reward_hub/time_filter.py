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
