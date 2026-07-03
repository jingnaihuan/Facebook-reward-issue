import reward_hub.config_store as cs


def _store(tmp_path):
    return cs.ConfigStore(str(tmp_path / "presets.json"))


def test_save_and_load(tmp_path):
    store = _store(tmp_path)
    store.save_preset("先锋活动", {"dedup_strategy": "earliest",
                                    "target_langs": ["en"]})
    got = store.load_preset("先锋活动")
    assert got["dedup_strategy"] == "earliest"
    assert got["target_langs"] == ["en"]


def test_list_presets(tmp_path):
    store = _store(tmp_path)
    store.save_preset("A", {"target_langs": ["en"]})
    store.save_preset("B", {"target_langs": ["de"]})
    assert set(store.list_presets()) == {"A", "B"}


def test_set_and_get_default(tmp_path):
    store = _store(tmp_path)
    store.save_preset("A", {"target_langs": ["en"]})
    store.set_default("A")
    assert store.get_default() == "A"


def test_persists_across_instances(tmp_path):
    p = str(tmp_path / "presets.json")
    cs.ConfigStore(p).save_preset("A", {"target_langs": ["en"]})
    assert "A" in cs.ConfigStore(p).list_presets()


def test_load_missing_returns_none(tmp_path):
    assert _store(tmp_path).load_preset("nope") is None
