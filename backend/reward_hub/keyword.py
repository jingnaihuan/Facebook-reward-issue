# -*- coding: utf-8 -*-
"""关键词抽奖的匹配层：解析关键词串 + 判定一条留言是否「答对」。

要点：
- 判定前先把玩家ID从留言里剔除——正答若是数字（如「12」），不能因为玩家ID
  （1 开头 10 位）里恰好含该数字而误判答对。见 [[extract_id]]。
- 大小写不敏感、子串包含、多关键词命中任一即算对。
"""
import re

_SEP = re.compile(r"[,，、\n\r]+")   # 半/全角逗号、顿号、换行都算分隔


def parse_keywords(raw):
    """把用户填写的关键词串拆成小写关键词列表：按分隔符切分、去首尾空格、丢空项。
    词内空格保留（支持多词答案，如 "red car"）。空串返回 []。"""
    if not raw:
        return []
    return [k for k in (s.strip().lower() for s in _SEP.split(str(raw))) if k]


def is_answered(content, player_id, keywords):
    """留言是否答对：剔除玩家ID后，正文（小写）包含任一关键词即为 True。
    keywords 为 parse_keywords 的输出（已小写）。keywords 为空恒 False。"""
    if not keywords:
        return False
    text = str(content or "")
    if player_id:
        text = text.replace(str(player_id), " ")   # 剔除全部ID出现，避免ID内数字充作答案
    text = text.lower()
    return any(k in text for k in keywords)
