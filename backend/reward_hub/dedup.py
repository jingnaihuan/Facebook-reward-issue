# -*- coding: utf-8 -*-
"""按玩家去重：earliest / all / best_likes。输出按 order 升序。"""


def dedup(rows, strategy="earliest"):
    if strategy == "all":
        return sorted(rows, key=lambda r: r["order"])

    best = {}
    for r in rows:
        pid = r["player_id"]
        cur = best.get(pid)
        if cur is None:
            best[pid] = r
        elif strategy == "earliest":
            if r["order"] < cur["order"]:
                best[pid] = r
        elif strategy == "best_likes":
            if r["likes"] > cur["likes"] or (
                r["likes"] == cur["likes"] and r["order"] < cur["order"]):
                best[pid] = r
        else:
            raise ValueError("未知去重策略: %s" % strategy)
    return sorted(best.values(), key=lambda r: r["order"])
