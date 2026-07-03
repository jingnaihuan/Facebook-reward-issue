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
