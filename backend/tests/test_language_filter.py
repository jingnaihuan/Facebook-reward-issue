from reward_hub.language_filter import filter_by_language


def _p(pid, lang):
    return {"player_id": pid, "lang": lang}


def test_keeps_target_langs():
    rows = [_p("1", "en"), _p("2", "de"), _p("3", "en")]
    passed, rejected = filter_by_language(rows, {"en"})
    assert [r["player_id"] for r in passed] == ["1", "3"]
    assert [r["player_id"] for r in rejected] == ["2"]


def test_rejected_have_reason():
    _, rejected = filter_by_language([_p("2", "de")], {"en"})
    assert rejected[0]["reject_reason"] == "语言不符"


def test_multi_target_langs():
    rows = [_p("1", "en"), _p("2", "fr"), _p("3", "de")]
    passed, _ = filter_by_language(rows, {"en", "fr"})
    assert {r["player_id"] for r in passed} == {"1", "2"}


def test_case_insensitive():
    passed, _ = filter_by_language([_p("1", "EN")], {"en"})
    assert len(passed) == 1
