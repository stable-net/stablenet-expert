#!/usr/bin/env python3
"""run_retrieval.py — 4-way (α/β/γ/δ) context retrieval for the ckg testset.

테스트 input(키워드/문장) -> grep(α) or ckg(β/γ/δ) -> 응답 컨텍스트 저장 -> 결정적 채점.
LLM은 이 단계에서 호출하지 않는다(검색만). 평가(관련성/충분성)는 judge 단계에서 별도.

  α  파일 원문 그대로 (기준선, grep — 우리 시스템 미사용)
  β  그래프 전체를 한꺼번에 (cks get_subgraph 광역 덤프)
  γ  필요한 정보를 개별 조회 (cks semantic_search -> find_symbol -> get_subgraph)
  δ  자동 선별 한 번에 (cks get_for_task)

결정적 지표: 위치 정확도(expected_files 포함 여부 recall/precision), 토큰 사용량,
오류 건수(실존하지 않는 파일 참조 수). 저장: runs/<method>/<id>.txt + results.jsonl
"""
from __future__ import annotations
import json, os, re, subprocess, collections, sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)
# go-stablenet checkout: env override, else the sibling of the coding-agent repo
ROOT = os.environ.get("GO_STABLENET_ROOT") or os.path.normpath(
    os.path.join(HERE, "..", "..", "..", "go-stablenet"))
BUILD_DIRS = ["consensus", "core", "systemcontracts", "eth", "params", "cmd", "common"]
_STOP = {"the","and","are","how","what","does","do","is","in","of","to","a","an","for","with",
         "which","where","when","why","that","this","go","stablenet","wbft","코드","파일","함수",
         "어떻게","무엇","어디","어느","왜","하는가","대한","그리고","또는","위한"}

def est_tokens(s): return len(s) // 4
def bare(sym):
    t = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", sym or "")
    return t[-1] if t else ""

def collect_locations(obj, out):
    if isinstance(obj, dict):
        f = obj.get("file")
        if isinstance(f, str) and f:
            out.append((f, obj.get("start_line"), obj.get("end_line")))
        for v in obj.values(): collect_locations(v, out)
    elif isinstance(obj, list):
        for v in obj: collect_locations(v, out)

# ---------- α: grep (no ckg) ----------
def _terms(entry):
    toks = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", entry["keyword"] + " " + entry["query"])
    seen = []
    for t in toks:
        if t.lower() not in _STOP and t not in seen:
            seen.append(t)
    return seen[:6]

def _grep_files(term):
    dirs = [os.path.join(ROOT, d) for d in BUILD_DIRS if os.path.isdir(os.path.join(ROOT, d))]
    try:
        r = subprocess.run(["grep", "-rlw", "--include=*.go", "--include=*.sol", term, *dirs],
                           capture_output=True, text=True, timeout=25)
        return [os.path.relpath(l, ROOT) for l in r.stdout.splitlines()
                if "_test" not in l and "/vendor/" not in l]
    except Exception:
        return []

def alpha(entry, cks=None):
    score = collections.Counter()
    for t in _terms(entry):
        for f in _grep_files(t):
            score[f] += 1
    def sz(f):
        p = os.path.join(ROOT, f)
        return os.path.getsize(p) if os.path.exists(p) else 1 << 30
    ranked = sorted(score.items(), key=lambda kv: (-kv[1], sz(kv[0])))
    top = [f for f, _ in ranked[:3]]
    parts, locs = [], []
    for f in top:
        try:
            body = open(os.path.join(ROOT, f), encoding="utf-8", errors="replace").read()
            parts.append(f"// ===== FILE: {f} =====\n{body}")
            locs.append((f, None, None))
        except Exception:
            pass
    return "\n\n".join(parts), locs

def _read_range(f, s, e):
    p = os.path.join(ROOT, _norm(f))
    try:
        lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
    except Exception:
        return ""
    if s and e and 1 <= s <= len(lines):
        return "\n".join(lines[s - 1:min(e, len(lines))])
    return "\n".join(lines[:80])

def _bodies_context(objs, locs, cap):
    """그래프 구조(요약) + 노드의 실제 코드 본문을 cap 한도 내에서 주입."""
    parts, seen, total = [], set(), 0
    for f, s, e in locs:
        key = (f, s, e)
        if key in seen:
            continue
        seen.add(key)
        body = _read_range(f, s, e)
        if not body:
            continue
        block = f"// ===== {f}:{s}-{e} =====\n{body}"
        if total + len(block) > cap:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)

# ---------- β: broad graph dump (+ 노드 본문) ----------
def beta(entry, cks):
    ss = cks("semantic_search", {"query": entry["query"], "k": 3, "exclude_tests": True, "expand": True})
    objs = [ss]
    for h in (ss.get("hits", []) if isinstance(ss, dict) else [])[:3]:
        name = bare(h.get("symbol", ""))
        if name:
            objs.append(cks("get_subgraph", {"symbol": name, "depth": 2, "max_total": 1500, "exclude_tests": True}))
    locs = []
    for o in objs: collect_locations(o, locs)
    return _bodies_context(objs, locs, 70000), locs

# ---------- γ: incremental targeted (+ 노드 본문) ----------
def gamma(entry, cks):
    ss = cks("semantic_search", {"query": entry["query"], "k": 5, "exclude_tests": True, "expand": True})
    objs = [ss]
    for h in (ss.get("hits", []) if isinstance(ss, dict) else [])[:3]:
        name = bare(h.get("symbol", ""))
        if not name: continue
        objs.append(cks("find_symbol", {"name": name, "exclude_tests": True}))
        objs.append(cks("get_subgraph", {"symbol": name, "depth": 1, "max_total": 200, "exclude_tests": True}))
    locs = []
    for o in objs: collect_locations(o, locs)
    return _bodies_context(objs, locs, 40000), locs

# ---------- δ: get_for_task (방식5 — ckv+ckg 하이브리드 자동선별) ----------
def delta(entry, cks):
    pack = cks("get_for_task", {"prompt": entry["query"]})
    locs = []
    collect_locations(pack, locs)
    return json.dumps(pack, ensure_ascii=False), locs

# ---------- ε: graph-only auto-select (방식4 — ckv 미사용) ----------
# Mirrors γ exactly except the seed comes from ckg BM25 text search
# (search_text) instead of ckv vector search (semantic_search). This
# isolates the ckv contribution: ε vs γ/δ = "what does the vector add?".
# glossary expand stays on for both (query rewriting is orthogonal to ckv).
def _fts_safe(q):
    # ckg's FTS5 backend treats ?, ", *, :, (), etc. as query syntax and errors
    # on a raw NL prompt. Keep only word characters (incl. Hangul) and spaces so
    # glossary expand can still match Korean aliases and append code keywords.
    return re.sub(r"[^\w\s]", " ", q, flags=re.UNICODE)

def epsilon(entry, cks):
    ss = cks("search_text", {"query": _fts_safe(entry["query"]), "k": 5, "exclude_tests": True, "expand": True})
    objs = [ss]
    for h in (ss.get("hits", []) if isinstance(ss, dict) else [])[:3]:
        name = bare(h.get("symbol", ""))
        if not name: continue
        objs.append(cks("find_symbol", {"name": name, "exclude_tests": True}))
        objs.append(cks("get_subgraph", {"symbol": name, "depth": 1, "max_total": 200, "exclude_tests": True}))
    locs = []
    for o in objs: collect_locations(o, locs)
    return _bodies_context(objs, locs, 40000), locs

METHODS = {"alpha": alpha, "beta": beta, "gamma": gamma, "epsilon": epsilon, "delta": delta}

# ---------- deterministic scoring ----------
def _norm(f):
    # strip a leading "./" ONLY (lstrip("./") would also eat the dot in ".claude/...")
    return f[2:] if f.startswith("./") else f

# Mirrors pkg/testpath.IsTest in code-knowledge-system so the benchmark's
# test-pollution metric matches what the exclude_tests filter actually drops.
# Test-only support files (testutil*.go, testdata/ etc.) count as tests.
_TEST_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx",
                  ".test.js", ".test.jsx", ".spec.js", ".spec.jsx")
_TEST_SEGMENTS = {"test", "tests", "testdata", "testutil", "testutils", "testhelpers"}

def is_test_file(f):
    f = _norm(f).replace("\\", "/")
    if not f:
        return False
    base = f.rsplit("/", 1)[-1]
    if base.endswith("_test.go"):
        return True
    if base.endswith(".go") and (base.startswith("testutil") or base.startswith("testhelper")):
        return True
    if base.endswith(_TEST_SUFFIXES):
        return True
    if base.endswith(".t.sol"):
        return True
    return any(seg in _TEST_SEGMENTS for seg in f.split("/"))

def score(entry, locs):
    surfaced = []
    for f, s, e in locs:
        nf = _norm(f)
        if nf not in [x[0] for x in surfaced]:
            surfaced.append((nf, s, e))
    exp = [_norm(f) for f in entry["expected_files"]]
    # answer_present: ground-truth answer file is in the surfaced set (same as location_hit)
    hit = any(sf in exp for sf, _, _ in surfaced)
    n_on_target = sum(1 for sf, _, _ in surfaced if sf in exp)
    # answer_focus: strict precision — how concentrated on the designated answer file(s)
    answer_focus = n_on_target / len(surfaced) if surfaced else 0.0
    recall = 1.0 if hit else 0.0
    errors = sum(1 for sf, _, _ in surfaced if not os.path.isfile(os.path.join(ROOT, sf)))
    test_files = [sf for sf, _, _ in surfaced if is_test_file(sf)]
    # surfaced_files: full list, no cap — the relevance judge needs every file
    return {"location_hit": hit, "answer_present": hit,
            "answer_focus": round(answer_focus, 3), "recall": recall,
            "n_surfaced": len(surfaced), "error_count": errors,
            "test_file_count": len(test_files),
            "test_pollution": 1 if test_files else 0,
            "surfaced_files": [sf for sf, _, _ in surfaced]}

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1, help="re-query N times to average cks retrieval noise")
    args = ap.parse_args()
    data = json.load(open(os.path.join(HERE, "queries.json")))["queries"]
    from stablenet_knowledge_client import make_stablenet_knowledge_client_from_env
    ctx = make_stablenet_knowledge_client_from_env()
    out = open(os.path.join(HERE, "results.jsonl"), "w")
    with ctx as cks:
        for run_i in range(1, args.runs + 1):
            for entry in data:
                for mname, fn in METHODS.items():
                    context, locs = fn(entry, cks)
                    sc = score(entry, locs)
                    # save context from the LAST run (used by the judge)
                    if run_i == args.runs:
                        d = os.path.join(HERE, "runs", mname); os.makedirs(d, exist_ok=True)
                        open(os.path.join(d, entry["id"] + ".txt"), "w", encoding="utf-8").write(context)
                    rec = {"run": run_i, "id": entry["id"], "domain": entry["domain"], "method": mname,
                           "tokens": est_tokens(context), **sc}
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
            print(f"-- run {run_i}/{args.runs} done")
    out.close()
    print("results.jsonl (runs averaged) + runs/<method>/<id>.txt written")

if __name__ == "__main__":
    main()
