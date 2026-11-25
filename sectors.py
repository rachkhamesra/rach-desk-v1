"""Sector clusters: several stocks of the same kind of business that are all near a breakout (or have just broken out) at once.

Sector here means a hand-kept group of businesses (config/sector_groups.csv: "Life insurers", "Private banks", "Cement" ...), finer than NSE's broad industries, in which
"Financial Services" holds banks, insurers, brokers and lenders together. A stock with no group is never part of a cluster; edit the file to add or change one.
A stock is a candidate when it is in the Breakout Bases scan near its breakout or just through it, or has an ascending triangle (or a rectangle at its top) that is a SETUP,
AT TOP or fresh BREAKOUT. A group with at least MIN_SIZE candidates is a cluster. Delivery is read alongside: each member's delivery against its own 20-session average today
and averaged over the last five sessions.
"""
import csv, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
GROUPS = os.path.join(HERE, "config", "sector_groups.csv")
MIN_SIZE = 3
HOT = 1.25            # delivery at least this multiple of its own average counts as above normal
LIGHT = 0.9


def load(path=GROUPS):
    try:
        with open(path, newline="", encoding="utf-8") as f: return {r["symbol"].strip(): r["group"].strip() for r in csv.DictReader(f) if r.get("symbol") and r.get("group")}
    except OSError:
        return {}


def candidates(M):
    """{symbol: dict(state 'NEAR' or 'BROKE OUT', why [str], brk_ratio)} for stocks near a breakout or through one."""
    out = {}

    def add(sym, state, why, brk=None):
        d = out.setdefault(sym, dict(state="NEAR", why=[], brk_ratio=None))
        if state == "BROKE OUT": d["state"] = "BROKE OUT"
        d["why"].append(why)
        if brk is not None and not pd.isna(brk): d["brk_ratio"] = max(d["brk_ratio"] or 0, float(brk))

    bases = M.get("breakout_bases")
    if bases is not None and len(bases):
        for r in bases.itertuples():
            if r.stage == "near": add(r.sym, "NEAR", "Breakout base · near breakout")
            elif r.stage == "fresh": add(r.sym, "BROKE OUT", "Breakout base · fresh breakout")
    for tf in ("daily", "weekly"):
        X = ((M.get("patterns") or {}).get(tf) or {}).get("found") or {}
        for kind, label in (("ascending", "Ascending triangle"), ("rectangle", "Rectangle")):
            for r in X.get(kind, []):
                st = r["status"]
                if st == "BREAKOUT": add(r["sym"], "BROKE OUT", f"{label} · {tf} · broke out", r.get("brk_ratio"))
                elif st in ("SETUP", "AT TOP"): add(r["sym"], "NEAR", f"{label} · {tf} · near the top")
    return out


def delivery(M, sym):
    """Delivery today and over the last five sessions, each against the stock's own 20-session average, or None."""
    if "RAT" not in M or sym not in M["RAT"]: return None, None
    s = M["RAT"][sym].dropna()
    return (float(s.iloc[-1]) if len(s) else None), (float(s.iloc[-5:].mean()) if len(s) else None)


def clusters(M, groups=None, min_size=MIN_SIZE):
    """[dict(group, members, n_near, n_broke, avg5, hot, tone)] for groups with at least min_size candidates, the largest first."""
    groups = groups if groups is not None else load()
    cand = candidates(M); by = {}
    for sym, d in cand.items():
        g = groups.get(sym)
        if not g: continue
        today, five = delivery(M, sym)
        by.setdefault(g, []).append(dict(sym=sym, state=d["state"], why=d["why"], brk_ratio=d["brk_ratio"], today=today, five=five))
    out = []
    for g, mem in by.items():
        if len(mem) < min_size: continue
        mem.sort(key=lambda m: (m["state"] != "BROKE OUT", -(m["five"] or 0)))
        fives = [m["five"] for m in mem if m["five"] is not None]; avg5 = float(np.mean(fives)) if fives else None
        tone = "NO DATA" if avg5 is None else "ABOVE NORMAL" if avg5 >= HOT else "LIGHT" if avg5 < LIGHT else "NORMAL"
        out.append(dict(group=g, members=mem, n_near=sum(m["state"] == "NEAR" for m in mem), n_broke=sum(m["state"] == "BROKE OUT" for m in mem), avg5=avg5,
                        hot=sum(1 for m in mem if (m["today"] or 0) >= HOT), tone=tone))
    out.sort(key=lambda c: (-len(c["members"]), -(c["avg5"] or 0)))
    return out


def by_symbol(cl):
    """{symbol: cluster} so a stock's page and cards can say which cluster it is in."""
    return {m["sym"]: c for c in cl for m in c["members"]}
