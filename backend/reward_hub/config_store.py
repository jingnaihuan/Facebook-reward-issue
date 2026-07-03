# -*- coding: utf-8 -*-
"""配置预设持久化（不含发奖规则）。"""
from reward_hub.common import load_json, save_json


class ConfigStore:
    def __init__(self, path):
        self.path = path

    def _data(self):
        return load_json(self.path, {"default": None, "presets": {}})

    def save_preset(self, name, config):
        d = self._data()
        d["presets"][name] = config
        save_json(self.path, d)

    def load_preset(self, name):
        return self._data()["presets"].get(name)

    def list_presets(self):
        return list(self._data()["presets"].keys())

    def set_default(self, name):
        d = self._data()
        d["default"] = name
        save_json(self.path, d)

    def get_default(self):
        return self._data()["default"]
