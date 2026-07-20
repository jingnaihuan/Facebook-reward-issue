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
