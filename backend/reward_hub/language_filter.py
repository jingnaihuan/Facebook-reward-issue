# -*- coding: utf-8 -*-
"""按语言筛选：命中目标语言的进 passed，其余进 rejected（带原因）。"""


def filter_by_language(rows, target_langs):
    targets = {t.lower() for t in target_langs}
    passed, rejected = [], []
    for r in rows:
        if str(r.get("lang", "")).lower() in targets:
            passed.append(r)
        else:
            rr = dict(r)
            rr["reject_reason"] = "语言不符"
            rejected.append(rr)
    return passed, rejected
