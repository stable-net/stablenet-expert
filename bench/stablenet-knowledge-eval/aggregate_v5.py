#!/usr/bin/env python3
"""Aggregate v5 metrics: deterministic (results.jsonl_full, 3-run) + judge (judged.jsonl)."""
import json, collections, sys

det = collections.defaultdict(lambda: {"n": 0, "present": 0, "focus": 0.0, "tok": 0, "testpoll": 0})
for l in open("results.jsonl_full"):
    d = json.loads(l)
    g = det[d["method"]]
    g["n"] += 1
    g["present"] += 1 if d["location_hit"] else 0
    g["focus"] += d["answer_focus"]
    g["tok"] += d["tokens"]
    g["testpoll"] += d.get("test_pollution", 0)

jud = collections.defaultdict(lambda: {"n": 0, "suf": 0, "rel": 0, "relp": 0.0, "rn": 0})
for l in open("judged.jsonl"):
    d = json.loads(l)
    g = jud[d["method"]]
    g["n"] += 1
    g["suf"] += 1 if d["judge"].get("sufficient") else 0
    g["rel"] += 1 if d["judge"].get("relevant") else 0
    rp = d.get("relevance", {}).get("relevance_precision")
    if rp is not None:
        g["relp"] += rp
        g["rn"] += 1

NAMES = {"alpha": "α grep", "beta": "β graph dump", "gamma": "γ incremental",
         "epsilon": "ε graph-only auto", "delta": "δ hybrid auto"}
print(f"{'method':<20}{'present':>9}{'focus':>8}{'rel-prec':>10}{'suffic':>9}{'tokens':>9}{'effic':>8}{'testpoll':>9}")
rows = {}
for m in ["alpha", "beta", "gamma", "epsilon", "delta"]:
    dg = det[m]; jg = jud[m]
    dn = dg["n"] or 1; jn = jg["n"] or 1; rn = jg["rn"] or 1
    present = 100 * dg["present"] / dn
    focus = dg["focus"] / dn
    relp = jg["relp"] / rn
    suf = 100 * jg["suf"] / jn
    tok = dg["tok"] / dn
    eff = suf / (tok / 1000) if tok else 0
    testpoll = f"{dg['testpoll']}/{dg['n']}"
    rows[m] = dict(present=present, focus=focus, relp=relp, suf=suf, tok=tok, eff=eff, testpoll=testpoll, jn=jn)
    print(f"{NAMES[m]:<20}{present:>8.0f}%{focus:>8.3f}{relp:>10.3f}{suf:>8.0f}%{tok:>9.0f}{eff:>8.2f}{testpoll:>9}")
print(f"\njudge cells per method (n): " + ", ".join(f"{m}={rows[m]['jn']}" for m in rows))
json.dump(rows, open("agg_v5.json", "w"), indent=2)
