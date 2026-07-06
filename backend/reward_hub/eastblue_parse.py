# -*- coding: utf-8 -*-
"""解析 Eastblue 导出 xlsx → {player_id: 玩家信息}。"""
import datetime
import openpyxl

# Eastblue 表头中文 → 内部字段（表头以实测为准，命名有出入在此调整）
_HEADER_MAP = {
    "玩家ID": "player_id", "语言": "lang", "别墅等级": "villa",
    "角色名称": "role_name", "角色等级": "role_level",
    "角色创建时间": "role_created", "服务器": "server",
    "历史充值总额": "total_recharge", "最后登录时间": "last_login",
}


def _cell(v):
    """把单元格值规整为 JSON 可序列化的形式（日期/时间转字符串）。"""
    if isinstance(v, datetime.datetime):
        # openpyxl 把纯日期列也读成 datetime(午夜)，此时只显示日期更干净
        if (v.hour, v.minute, v.second, v.microsecond) == (0, 0, 0, 0):
            return v.strftime("%Y-%m-%d")
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, datetime.date):
        return v.strftime("%Y-%m-%d")
    return v


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
            rec[field] = _cell(row[i]) if i < len(row) else ""
        pid = rec.get("player_id")
        if pid:
            rec["player_id"] = str(pid)
            players[str(pid)] = rec
    return players
