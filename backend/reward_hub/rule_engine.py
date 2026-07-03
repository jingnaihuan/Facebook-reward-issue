# -*- coding: utf-8 -*-
"""发奖规则引擎：四种选取规则 + 多奖项按序结算（不重复中奖）。"""
import random


def top_floors(rows, n):
    return sorted(rows, key=lambda r: r["order"])[:n]


def top_likes(rows, n):
    return sorted(rows, key=lambda r: (-r["likes"], r["order"]))[:n]


def top_replies(rows, n):
    return sorted(rows, key=lambda r: (-r["replies"], r["order"]))[:n]


def random_pick(rows, n, seed=0):
    pool = sorted(rows, key=lambda r: r["order"])  # 先定序，保证 seed 可复现
    rnd = random.Random(seed)
    rnd.shuffle(pool)
    return pool[:n]


_RULES = {
    "top_floors": lambda rows, a: top_floors(rows, a["n"]),
    "top_likes": lambda rows, a: top_likes(rows, a["n"]),
    "top_replies": lambda rows, a: top_replies(rows, a["n"]),
    "random_pick": lambda rows, a: random_pick(rows, a["n"], a.get("seed", 0)),
}


def run_awards(rows, awards):
    """按顺序结算奖项，已中奖玩家从后续池剔除。
    返回 (result: {award_name: [winners]}, remaining: [未中奖])。"""
    pool = list(rows)
    result = {}
    for a in awards:
        rule = _RULES.get(a["rule"])
        if rule is None:
            raise ValueError("未知规则: %s" % a["rule"])
        winners = rule(pool, a)
        result[a["name"]] = winners
        won_ids = {w["player_id"] for w in winners}
        pool = [r for r in pool if r["player_id"] not in won_ids]
    return result, pool
