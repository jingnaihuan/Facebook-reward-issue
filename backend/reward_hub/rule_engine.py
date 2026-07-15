# -*- coding: utf-8 -*-
"""发奖规则引擎：选取规则 + 多奖项按序结算（不重复中奖）。

奖项分两类：
- 普通奖：在「去重后一人一条」的池(rows)上按规则选。
- 关键词奖：奖项带 keyword 时，只在「答对」的人里选，且代表留言取自该玩家的
  『全部留言』(all_comments)而非去重那条——先错后对时用答对那条的楼层/点赞。
  详见 [[keyword]]。规则 answered_all = 答对即得(全发，不限人数)。
"""
import random

from .keyword import parse_keywords, is_answered


def top_floors(rows, n):
    return sorted(rows, key=lambda r: r["order"])[:n]


def top_likes(rows, n):
    # 只有真点过赞(>0)的人才有资格：不足 N 就给实际人数，不用 0 赞的凑数。
    eligible = [r for r in rows if r["likes"] > 0]
    return sorted(eligible, key=lambda r: (-r["likes"], r["order"]))[:n]


def top_replies(rows, n):
    eligible = [r for r in rows if r["replies"] > 0]
    return sorted(eligible, key=lambda r: (-r["replies"], r["order"]))[:n]


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

# answered_all（全部命中/答对即得）不抽选、不限人数，单独处理，不在 _RULES 里。
_ANSWERED_ALL = "answered_all"


def _better_rep(cand, cur, rule):
    """同一玩家的多条『答对』留言里，按奖项规则口径判断 cand 是否比 cur 更该当代表：
    点赞奖取点赞最高、回复奖取回复最高（平局取更早楼层）；其余(楼层/随机/全发)取最早。"""
    if rule == "top_likes":
        return (cand["likes"], -cand["order"]) > (cur["likes"], -cur["order"])
    if rule == "top_replies":
        return (cand["replies"], -cand["order"]) > (cur["replies"], -cur["order"])
    return cand["order"] < cur["order"]


def _representatives(comments, rule):
    """把答对留言按玩家收敛成一人一条『代表留言』（口径随 rule，见 _better_rep）。"""
    best = {}
    for r in comments:
        pid = r["player_id"]
        cur = best.get(pid)
        if cur is None or _better_rep(r, cur, rule):
            best[pid] = r
    return list(best.values())


def _keyword_winners(award, source, won_ids):
    """关键词奖选取：从 source 里挑『未中奖 + 答对』的留言，收敛成代表后按规则选。"""
    kws = parse_keywords(award.get("keyword", ""))
    correct = [r for r in source
               if r["player_id"] not in won_ids
               and is_answered(r.get("content", ""), r.get("player_id"), kws)]
    reps = _representatives(correct, award["rule"])
    if award["rule"] == _ANSWERED_ALL:
        return sorted(reps, key=lambda r: r["order"])   # 答对即得：全发，按楼层排序
    return _RULES[award["rule"]](reps, award)


def _validate(award):
    """校验奖项配置（第二道防线，前端也拦）。返回该奖项是否为关键词奖。"""
    rule = award.get("rule")
    kw = parse_keywords(award.get("keyword", ""))
    if rule == _ANSWERED_ALL:
        if not kw:
            raise ValueError("奖项「%s」用『全部命中』规则时必须填写关键词" % award.get("name", "?"))
        return True
    if rule not in _RULES:
        raise ValueError("未知规则: %s" % rule)
    # 数量必须是正整数：拦住「数量为 0/空」这类会算出错误名单的输入。
    # 全员发放请走「普惠奖」= 不传任何奖项(awards 为空)，不会进入此循环。
    n = award.get("n")
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        raise ValueError("奖项「%s」的数量必须为大于 0 的整数" % award.get("name", "?"))
    return bool(kw)


def run_awards(rows, awards, all_comments=None):
    """按顺序结算奖项，已中奖玩家从后续所有奖项（普通/关键词）池中剔除。
    rows: 去重后一人一条的池（普通奖用）。
    all_comments: 全量有效留言（一人可多条），关键词奖据此判『答对』并取代表留言；
                  未提供时关键词奖回退到在 rows 上匹配（即只看去重那条）。
    返回 (result: {award_name: [winners]}, remaining: [未中奖])。"""
    won_ids = set()
    result = {}
    kw_source = all_comments if all_comments is not None else rows
    for a in awards:
        is_kw = _validate(a)
        if is_kw:
            winners = _keyword_winners(a, kw_source, won_ids)
        else:
            candidates = [r for r in rows if r["player_id"] not in won_ids]
            winners = _RULES[a["rule"]](candidates, a)
        result[a["name"]] = winners
        won_ids.update(w["player_id"] for w in winners)
    remaining = [r for r in rows if r["player_id"] not in won_ids]
    return result, remaining
