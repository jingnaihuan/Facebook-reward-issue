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
