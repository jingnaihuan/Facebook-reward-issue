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


def export_reward_workbook(path, awards, participation, invalid,
                           allow_winner_participation=False):
    """awards: {奖项名: [玩家]}；participation: [玩家]；invalid: [无效记录]。
    allow_winner_participation：参与奖是否含抽选中奖者（仅用于 sheet 标题标注）。"""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, winners in awards.items():
        _write_player_sheet(wb.create_sheet(title=name[:31]), winners)
    # 无任何抽选奖项 = 普惠奖（全员）：这些人是发奖对象，工作簿名标清；
    # 有抽选奖项时，这一档是落选者的「参与奖」；若允许中奖者重复领，则标注「含中奖者」。
    if not awards:
        part_title = "普惠奖（全员）"
    elif allow_winner_participation:
        part_title = "参与奖（含中奖者）"
    else:
        part_title = "参与奖"
    _write_player_sheet(wb.create_sheet(title=part_title), participation)
    _write_invalid_sheet(wb.create_sheet(title="无效"), invalid)
    wb.save(path)
    return path
