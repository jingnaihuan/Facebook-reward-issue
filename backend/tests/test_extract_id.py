from reward_hub.extract_id import extract_id


def test_plain_id():
    assert extract_id("1052837435 Row 3, Column 1") == "1052837435"


def test_id_after_colon():
    assert extract_id("ID: 1093454463 name") == "1093454463"


def test_id_at_line_start():
    assert extract_id("1050551037 + row 3") == "1050551037"


def test_reject_11_digits():
    # 11 位数字不应被当作 10 位 ID 的一部分
    assert extract_id("21065202703 something") is None


def test_no_id():
    assert extract_id("hello world no digits") is None


def test_id_not_starting_with_1():
    assert extract_id("2050551037 abc") is None


def test_first_match_only():
    assert extract_id("1052837435 and 1093454463") == "1052837435"
