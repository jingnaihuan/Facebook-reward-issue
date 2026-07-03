# -*- coding: utf-8 -*-
"""公共工具：数据目录、JSON 读写、子脚本 emit/log。"""
import os, sys, json


def app_data_dir():
    d = os.path.expanduser("~/.reward_hub_app")
    os.makedirs(d, exist_ok=True)
    return d


def work_dir():
    d = os.path.expanduser("~/Documents/发奖中台工作区")
    os.makedirs(d, exist_ok=True)
    return d


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def emit(obj):
    """子脚本向 server 回一行 JSON。"""
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()


def log(tag, msg):
    print("[%s] %s" % (tag, msg), flush=True)
