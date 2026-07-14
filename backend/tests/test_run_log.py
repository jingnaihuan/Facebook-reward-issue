# -*- coding: utf-8 -*-
"""结算运行日志：每次结算落一份含时间/规则/种子/各名单的 JSON，供事后查证发奖对象。"""
import json
import server


def _out():
    return {
        "awards": {"先锋奖": [{"player_id": "1000000001"}, {"player_id": "1000000002"}]},
        "participation": [{"player_id": "1000000003"}],
        "invalid": [{"player_id": "", "reject_reason": "无有效ID"}],
    }


def test_run_log_records_awards_seed_and_names(tmp_path, monkeypatch):
    monkeypatch.setattr(server.common, "work_dir", lambda: str(tmp_path))
    inputs = {"dedup_strategy": "earliest", "target_langs": ["en"],
              "awards": [{"name": "先锋奖", "rule": "random_pick", "n": 2, "seed": 7}]}
    path = server.write_run_log(inputs, _out())

    assert path and path.endswith(".json")
    rec = json.loads(open(path, encoding="utf-8").read())
    assert rec["模式"] == "抽选"
    assert rec["奖项配置"][0]["seed"] == 7                       # 种子入档，随机可复现
    assert rec["各奖项中奖"]["先锋奖"] == ["1000000001", "1000000002"]
    assert rec["参与奖（未中奖）"] == ["1000000003"]
    assert rec["无效"][0]["原因"] == "无有效ID"


def test_run_log_labels_participation_including_winners(tmp_path, monkeypatch):
    """开「中奖者可重复领参与奖」：日志里参与奖标签改为「参与奖（含中奖者）」。"""
    monkeypatch.setattr(server.common, "work_dir", lambda: str(tmp_path))
    inputs = {"dedup_strategy": "earliest", "target_langs": ["en"],
              "awards": [{"name": "先锋奖", "rule": "top_floors", "n": 2}],
              "allow_winner_participation": True}
    path = server.write_run_log(inputs, _out())

    rec = json.loads(open(path, encoding="utf-8").read())
    assert rec["模式"] == "抽选"
    assert rec["参与奖（含中奖者）"] == ["1000000003"]
    assert "参与奖（未中奖）" not in rec


def test_run_log_universal_labels_participation(tmp_path, monkeypatch):
    monkeypatch.setattr(server.common, "work_dir", lambda: str(tmp_path))
    inputs = {"dedup_strategy": "earliest", "target_langs": ["en"], "awards": []}
    out = {"awards": {}, "participation": [{"player_id": "1000000009"}], "invalid": []}
    path = server.write_run_log(inputs, out)

    rec = json.loads(open(path, encoding="utf-8").read())
    assert rec["模式"] == "普惠奖（全员）"
    assert rec["普惠奖（全员）"] == ["1000000009"]


def test_run_log_never_raises(monkeypatch):
    """日志目录不可写等异常绝不能影响发奖：写失败应静默返回 None。"""
    monkeypatch.setattr(server.common, "work_dir", lambda: "/proc/nonexistent-\0-bad")
    assert server.write_run_log({"awards": []}, _out()) is None
