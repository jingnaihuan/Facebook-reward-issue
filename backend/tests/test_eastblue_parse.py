import datetime
import json

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


def test_parse_datetime_cells_are_json_serializable(tmp_path):
    """真实 Eastblue 表的日期列是 datetime，需转成字符串否则 JSON 序列化会崩。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["玩家ID", "语言", "别墅等级", "角色名称", "角色等级",
               "角色创建时间", "服务器", "历史充值总额", "最后登录时间"])
    ws.append(["1052837435", "en", 37, "Kraken", 55,
               datetime.date(2019, 5, 2), "S177", 87024.93,
               datetime.datetime(2026, 7, 3, 14, 30, 0)])
    p = tmp_path / "eb_dt.xlsx"
    wb.save(str(p))
    players = parse_players(str(p))
    rec = players["1052837435"]
    assert rec["role_created"] == "2019-05-02"
    assert rec["last_login"] == "2026-07-03 14:30:00"
    json.dumps(players)   # 不应抛 "Object of type datetime is not JSON serializable"
