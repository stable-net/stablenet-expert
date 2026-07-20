#!/usr/bin/env python3
"""run_judge.py — 평가: 검색된 컨텍스트의 관련성·설계충분성을 LLM이 판정.

요구사항(평가#1): "응답 결과의 내용으로 llm이 얻는 정보가 input(쿼리)에 대한 내용으로
구성됐는지, 그 정보로 기능 수정 등 설계 작업이 가능한지" 판정 + 토큰은 검색단계에서 측정.

robustness(지난 Haiku 실패 교훈): 시스템 프롬프트로 JSON만 강제 + 정규식 폴백 파싱 +
1회 재시도 + 기본 모델 사용. 컨텍스트는 비용 한정 위해 ~20k자(=~5k토큰)로 절단(절단표시).
판정 입력은 '쿼리 + 검색 컨텍스트'뿐 — 정답(expected)은 절대 주지 않음.

relevance_precision: 서피스된 파일 각각이 쿼리 답변/설계에 얼마나 관련있는지 LLM 판정.
  relevant_indices는 1-based 인덱스 목록. 관련 있는 파일 수 / 전체 서피스 파일 수.

Usage:
  python3 run_judge.py [--model <id>] [--cap-chars 20000] [--votes N]
  python3 run_judge.py --self-test   # offline unit check, no LLM calls
"""
from __future__ import annotations
import json, os, re, subprocess, argparse, sys

HERE = os.path.dirname(os.path.abspath(__file__))
_SYS = (
    "You evaluate a RETRIEVED CODE CONTEXT for a developer question about the go-stablenet "
    "(Go blockchain) codebase. Judge ONLY from the provided context (not prior knowledge):\n"
    "- relevant: the context is about the question's topic (the right area of code).\n"
    "- sufficient: it contains enough of the actual code (the relevant function/type and its "
    "body) that a developer could modify or design that feature from it.\n"
    "- answer_present: the specific code the question asks about is literally present in the context.\n"
    "Respond with ONLY a JSON object on one line, no prose:\n"
    '{"relevant": true|false, "sufficient": true|false, "answer_present": true|false}'
)

_SYS_RELEVANCE = (
    "You classify which files from a retrieved file list are relevant to a developer question "
    "about the go-stablenet (Go blockchain) codebase.\n"
    "A file is RELEVANT if it is: the direct answer target, a caller/callee of the answer, "
    "a type/interface used by the answer, or a related contract/component needed for design "
    "decisions about the feature in the question.\n"
    "A file is NOT relevant if it is: clearly unrelated infrastructure, a package with no "
    "connection to the question's topic, or generic test scaffolding noise.\n"
    "Respond with ONLY strict JSON on one line, no prose:\n"
    '{"relevant_indices": [<1-based integers of relevant files>]}'
)


def judge(question, context, model, cap):
    if len(context) > cap:
        context = context[:cap] + "\n...[TRUNCATED]"
    user = f"QUESTION:\n{question}\n\nRETRIEVED CONTEXT:\n{context}"
    cmd = ["claude", "-p", "--output-format", "json", "--append-system-prompt", _SYS]
    if model:
        cmd += ["--model", model]
    for attempt in range(2):
        try:
            r = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=180)
            outer = json.loads(r.stdout)
            txt = outer.get("result", "") or ""
        except Exception as e:
            txt = ""
        # parse the model's JSON verdict
        try:
            obj = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
            return {k: bool(obj.get(k)) for k in ("relevant", "sufficient", "answer_present")}, txt[:200]
        except Exception:
            low = txt.lower()
            def grab(key):
                m = re.search(rf'"{key}"\s*:\s*(true|false)', low)
                return (m.group(1) == "true") if m else None
            v = {k: grab(k) for k in ("relevant", "sufficient", "answer_present")}
            if any(x is not None for x in v.values()):
                return {k: bool(x) for k, x in v.items()}, txt[:200]
    return {"relevant": None, "sufficient": None, "answer_present": None}, "PARSE_FAIL"


def _parse_relevance_response(txt, n_files):
    """Parse {"relevant_indices": [...]} from LLM text.

    Returns a set of valid 1-based indices (clipped to [1, n_files]).
    Returns None on total parse failure.
    """
    try:
        obj = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
        indices = obj.get("relevant_indices")
        if not isinstance(indices, list):
            return None
        valid = {int(i) for i in indices if isinstance(i, (int, float)) and 1 <= int(i) <= n_files}
        return valid
    except Exception:
        # regex fallback: extract all integers from a relevant_indices array
        m = re.search(r'"relevant_indices"\s*:\s*\[([^\]]*)\]', txt)
        if not m:
            return None
        raw = m.group(1)
        nums = re.findall(r'\d+', raw)
        valid = {int(n) for n in nums if 1 <= int(n) <= n_files}
        return valid if nums else None


def judge_relevance(question, surfaced_files, model):
    """Call LLM once to classify per-file relevance for surfaced_files.

    Returns a dict:
      {"relevant": N, "total": M, "relevance_precision": float|None,
       "relevant_indices": [<1-based>]}
    On parse failure: relevance_precision is None.
    """
    n = len(surfaced_files)
    if n == 0:
        return {"relevant": 0, "total": 0, "relevance_precision": 0.0, "relevant_indices": []}

    file_list = "\n".join(f"{i+1}. {f}" for i, f in enumerate(surfaced_files))
    user = (
        f"QUESTION:\n{question}\n\n"
        f"SURFACED FILES (repo-relative paths):\n{file_list}\n\n"
        "Which of these files are relevant to answering or implementing/modifying "
        "the feature described in the question? Include the target code AND genuinely "
        "useful related/design context (callers, callees, types, related contracts). "
        "Exclude clearly-unrelated files."
    )
    cmd = ["claude", "-p", "--output-format", "json", "--append-system-prompt", _SYS_RELEVANCE]
    if model:
        cmd += ["--model", model]

    txt = ""
    for attempt in range(2):
        try:
            r = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=180)
            outer = json.loads(r.stdout)
            txt = outer.get("result", "") or ""
        except Exception:
            txt = ""
        indices = _parse_relevance_response(txt, n)
        if indices is not None:
            precision = len(indices) / n
            return {
                "relevant": len(indices),
                "total": n,
                "relevance_precision": round(precision, 3),
                "relevant_indices": sorted(indices),
            }

    return {"relevant": None, "total": n, "relevance_precision": None, "relevant_indices": []}


def _self_test():
    """Offline unit check for relevance JSON parsing — no LLM calls."""
    print("Running self-test...")
    errors = []

    # Test 1: clean JSON parse, 2 of 4 relevant → precision 0.5
    txt1 = '{"relevant_indices": [1, 3]}'
    result = _parse_relevance_response(txt1, 4)
    assert result == {1, 3}, f"Test 1 failed: {result}"
    precision = len(result) / 4
    assert abs(precision - 0.5) < 1e-9, f"Test 1 precision failed: {precision}"
    print("  Test 1 PASS: clean JSON {1,3} over 4 files → precision 0.5")

    # Test 2: regex fallback when braces wrap extra prose
    txt2 = 'Sure thing!\n{"relevant_indices": [2, 4]}\nDone.'
    result = _parse_relevance_response(txt2, 4)
    assert result == {2, 4}, f"Test 2 failed: {result}"
    print("  Test 2 PASS: JSON embedded in prose → regex fallback extracts {2,4}")

    # Test 3: out-of-range indices are filtered
    txt3 = '{"relevant_indices": [0, 1, 5, 99]}'
    result = _parse_relevance_response(txt3, 4)
    assert result == {1}, f"Test 3 failed: {result}"
    print("  Test 3 PASS: indices 0,5,99 out of range for 4 files → only {1} kept")

    # Test 4: total parse failure returns None
    txt4 = "I cannot determine relevance."
    result = _parse_relevance_response(txt4, 4)
    assert result is None, f"Test 4 failed: {result}"
    print("  Test 4 PASS: unparseable text → None")

    # Test 5: empty indices list
    txt5 = '{"relevant_indices": []}'
    result = _parse_relevance_response(txt5, 4)
    assert result == set(), f"Test 5 failed: {result}"
    print("  Test 5 PASS: empty indices list → empty set → precision 0.0")

    # Test 6: all files relevant
    txt6 = '{"relevant_indices": [1, 2, 3]}'
    result = _parse_relevance_response(txt6, 3)
    assert result == {1, 2, 3}, f"Test 6 failed: {result}"
    precision = len(result) / 3
    assert abs(precision - 1.0) < 1e-9, f"Test 6 precision failed: {precision}"
    print("  Test 6 PASS: all 3 files relevant → precision 1.0")

    print("All self-tests PASSED.")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--cap-chars", type=int, default=20000)
    ap.add_argument("--votes", type=int, default=3, help="judge N times, majority vote (noise reduction)")
    ap.add_argument("--self-test", action="store_true", help="run offline unit checks and exit (no LLM calls)")
    args = ap.parse_args()

    if args.self_test:
        ok = _self_test()
        sys.exit(0 if ok else 1)

    queries = {q["id"]: q for q in json.load(open(os.path.join(HERE, "queries.json")))["queries"]}
    rows = [json.loads(l) for l in open(os.path.join(HERE, "results.jsonl"))]
    out = open(os.path.join(HERE, "judged.jsonl"), "w")
    for i, rec in enumerate(rows):
        q = queries[rec["id"]]
        ctx_path = os.path.join(HERE, "runs", rec["method"], rec["id"] + ".txt")
        context = open(ctx_path, encoding="utf-8", errors="replace").read() if os.path.exists(ctx_path) else ""
        votes = [judge(q["query"], context, args.model, args.cap_chars)[0] for _ in range(args.votes)]
        verdict, tally = {}, {}
        for k in ("relevant", "sufficient", "answer_present"):
            yes = sum(1 for v in votes if v.get(k) is True)
            no = sum(1 for v in votes if v.get(k) is False)
            verdict[k] = (yes >= no) if (yes + no) else None
            tally[k] = f"{yes}/{yes+no}"

        # relevance_precision: single LLM call classifying each surfaced file
        surfaced = rec.get("surfaced_files", [])
        relevance = judge_relevance(q["query"], surfaced, args.model)

        rec = {**rec, "judge": verdict, "votes": tally, "relevance": relevance}
        out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
        rp = relevance.get("relevance_precision")
        rp_str = f"{rp:.3f}" if rp is not None else "null"
        print(f"[{i+1}/{len(rows)}] {rec['id']} {rec['method']:<6} "
              f"rel={verdict['relevant']}({tally['relevant']}) "
              f"suf={verdict['sufficient']}({tally['sufficient']}) "
              f"rel_prec={rp_str}")
    out.close()
    print("\njudged.jsonl written")

if __name__ == "__main__":
    main()
