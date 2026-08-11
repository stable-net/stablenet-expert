---
description: Give it a symptom and it finds the root cause, reports it, and stops — touching neither code nor a PR.
argument-hint: "\"<what goes wrong, and how>\"  [--path <file/directory to narrow to>]"
---

# /core-dev:diagnose

Take a symptom and report **only what the root cause is**. Unlike
`/core-dev:work-with-prompt` it does **not** carry on into design, implementation, tests or a PR
— this is **read-only diagnosis**.

Internally it reuses `analyzer` (situation analysis plus the root-cause stage, with
stablenet-knowledge retrieval and root-cause-lifecycle) in **diagnose mode**: it **stops** as
soon as the root cause is established and produces `diagnosis.md`. It writes no reproduction
test, modifies no code, creates no branch, and does not advance to PLANNING.

> When to use it: to work out "why is this happening?" quickly. To have the fix carried out
> autonomously as well, use `/core-dev:work-with-prompt` instead.

---

## 0. Argument shape
- Basic: `/core-dev:diagnose "some transactions are wrongly rejected right after an epoch change"`
- Scope hint (optional): `... --path core/txpool` — the path the planner looks at first (without
  it, stablenet-knowledge searches broadly).

---

## 1. Validate the argument
```
1.1. The quoted body -> problem_text. Option --path <path> -> focus_path (optional).
1.2. Empty body -> print usage and stop:
     "usage: /core-dev:diagnose \"<symptom / problem description>\" [--path <path>]"
```

## 2. Job directory (diagnoses are kept apart from tickets)
```
2.1. bash: git rev-parse --show-toplevel -> repo_root (on failure stop: "run inside a git repo")
2.2. bash: date -u +"%Y%m%d_%H%M%S" -> timestamp
2.3. workspace = "{repo_root}/.stablenet-expert/diagnoses/DIAG-{timestamp}"
2.4. bash: mkdir -p {workspace}
2.5. Auto-redact local secrets: replace obvious secrets in problem_text
     (sk-/ghp_/-----BEGIN/tokens/passwords) with "[REDACTED]" (never a hard stop).
```

## 3. Dispatch the analyzer (diagnosis only — situation + root cause)
```
3.1. Agent(
       subagent_type="analyzer",
       description="Diagnose root cause for DIAG-{timestamp}",
       prompt=
         "DIAGNOSE MODE — read-only root-cause analysis. Do the ANALYSIS phase ONLY.\n"
         "workspace_dir={workspace}\n"
         "problem: {problem_text}\n"
         "focus_path: {focus_path or '(none — search broadly via stablenet-knowledge)'}\n"
         "\n"
         "Use stablenet-knowledge (semantic_search / get_for_task / find_callers / get_subgraph /\n"
         "impact_analysis / change_history) to locate candidate code. Then REASON to\n"
         "the cause with the `root-cause-lifecycle` skill: pick the single value the\n"
         "symptom is about, enumerate EVERY copy/cache of it, find which lifecycle edge\n"
         "(produce/store/consume) is broken, TRACE a stale value to its source (the\n"
         "first cache is usually the symptom, not the cause), and FALSIFY competing\n"
         "hypotheses with the symptom's distinguishing feature. Then write\n"
         "{workspace}/diagnosis.md with EXACTLY these sections:\n"
         "  1. Root cause — the single most likely cause, stated plainly, naming the\n"
         "     broken lifecycle edge and the competing hypothesis you ruled out (why).\n"
         "  2. Evidence — file:line citations + relevant call/relation edges from stablenet-knowledge.\n"
         "  3. Affected sites — every place that would need to change to fix it\n"
         "     (write-site enumeration via find_callers/impact_analysis), or 'n/a'.\n"
         "  4. Confidence — high/medium/low + what would raise it.\n"
         "  5. Suggested direction — a one-paragraph fix approach (NOT a full plan).\n"
         "\n"
         "STRICT (diagnose mode): do ONLY situation analysis + root cause. You MAY write a\n"
         "THROWAWAY investigative probe (investigative-probe skill) to disambiguate competing\n"
         "candidates at runtime, then REVERT it (do not keep it). Do NOT author the\n"
         "reproduction test (the fix oracle), do NOT modify production code, do NOT write\n"
         "plan.md or any design, do NOT create a branch, do NOT transition the pipeline (stay\n"
         "in ANALYSIS), do NOT dispatch other agents. End after writing diagnosis.md."
     )
```

## 4. Report the result
```
4.1. Read {workspace}/diagnosis.md and summarize for the user:
     - the root cause in one line
     - two or three key pieces of evidence (file:line)
     - confidence
     - "full diagnosis: {workspace}/diagnosis.md"
4.2. Note: "To carry on into the fix: /core-dev:work-with-prompt \"{problem_text}\""
```

## 5. Done when (checklist)
- [ ] An empty body prints usage
- [ ] A clear error outside a git repository
- [ ] A DIAG-{timestamp} diagnosis directory created (separate from tickets)
- [ ] The analyzer does ANALYSIS only and produces diagnosis.md (no code, branch or PR changes)
- [ ] Root cause, evidence and confidence summarized
