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
