import openpyxl
from reward_hub.export import export_reward_workbook

PLAYER_COLS = ["留言顺序", "留言时间", "玩家ID", "语言", "别墅等级",
               "角色名称", "角色等级", "角色创建时间", "服务器",
               "历史充值总额", "最后登录时间"]


def _p(pid, order, lang="en"):
    return {"order": order, "time": "2026-06-26 08:00:00", "player_id": pid,
            "lang": lang, "villa": "37", "role_name": "Hero", "role_level": "55",
            "role_created": "2019-05-02", "server": "S177",
            "total_recharge": "100", "last_login": "2026-07-03"}


def test_creates_sheets(tmp_path):
    out = tmp_path / "out.xlsx"
    awards = {"先锋奖": [_p("1000000001", 1)]}
    participation = [_p("1000000002", 2)]
    invalid = [{"player_id": "", "content": "no id", "reject_reason": "无有效ID"}]
    export_reward_workbook(str(out), awards, participation, invalid)

    wb = openpyxl.load_workbook(str(out))
    assert wb.sheetnames == ["先锋奖", "参与奖", "无效"]


def test_award_sheet_header_and_row(tmp_path):
    out = tmp_path / "out.xlsx"
    export_reward_workbook(str(out), {"先锋奖": [_p("1000000001", 1)]}, [], [])
    wb = openpyxl.load_workbook(str(out))
    ws = wb["先锋奖"]
    assert [c.value for c in ws[1]] == PLAYER_COLS
    assert ws.cell(row=2, column=3).value == "1000000001"  # 玩家ID 列


def test_invalid_sheet_has_reason_column(tmp_path):
    out = tmp_path / "out.xlsx"
    invalid = [{"player_id": "", "content": "hi", "reject_reason": "无有效ID"}]
    export_reward_workbook(str(out), {}, [], invalid)
    wb = openpyxl.load_workbook(str(out))
    ws = wb["无效"]
    header = [c.value for c in ws[1]]
    assert "原因" in header
    assert ws.cell(row=2, column=header.index("原因") + 1).value == "无有效ID"
