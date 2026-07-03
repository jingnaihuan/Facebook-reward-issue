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
