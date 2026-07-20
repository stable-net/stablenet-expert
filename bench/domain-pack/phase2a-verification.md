# P1 Phase 2a — verification record (branch `p1-phase2-domain-pack-wire`, 2026-06-22)

Phase 2a rewired analyzer/planner/evaluator/bench-analyzer-skills from the
go-stablenet-specific skills to the generic `domain-pack` loader. Four verification
layers; **three pass here, the fourth needs a live full-pipeline run** (merge gate).

## ✅ 1. Content preservation (byte-level)
The moved domain content is identical to the original (no loss in the move).
```
diff <(git show b33931f:plugin/skills/stablenet-invariants/SKILL.md | sed -n '/^1\. /,$p') \
     <(sed -n '/^1\. /,$p' plugin/domains/go-stablenet/invariants.md)   → IDENTICAL (11 invariants + footer)
diff <(git show b33931f:plugin/skills/stablenet-context/SKILL.md | sed -n '/file_path contains/p') \
     <(sed -n '/file_path contains/p' plugin/domains/go-stablenet/context.md) → IDENTICAL (11 path rules)
```

## ✅ 2. Deterministic loader resolution
`project_id=go-stablenet` → `domain-pack.json` → referenced files resolve to real,
non-empty content: invariants.md (11 invariants), context.md (11 path rules).
(Reproduce: see `check.py` + the resolution snippet in the Phase-2a session log.)

## ✅ 3. Loader followability — live agent (the §3.1 reliability risk)
A fresh agent given ONLY the `domain-pack` loader skill (no prior go-stablenet
knowledge) was asked to resolve the pack, classify 4 paths, and quote 3 invariants.
Result — followed the loader end-to-end with **no ambiguity/guessing**:
- read exactly: `skills/domain-pack/SKILL.md` → `domains/go-stablenet/domain-pack.json`
  → `invariants.md` + `context.md`;
- classified consensus/wbft/core/core.go→consensus, core/txpool/...→txpool,
  eth/gasprice/anzeon.go→eth/les, miner/worker.go→miner (all correct);
- quoted EQUAL POWER / EPOCH-LENGTH ASYMMETRY / ROUND-CHANGE NEUTRALITY (correct);
- project_id fallback worked as specified.
→ Empirical evidence (not assertion) that the loader+runtime-Read mechanism is
  followable by an agent reading only the pack files.

## 🔶 4. Full-pipeline no-regression — merge-then-test runbook
Why not in the authoring session: the session dispatches the **installed plugin cache**
(`~/.claude/plugins/cache/coding-agent/coding-agent/<version>/`), not the branch working
tree — so any run there tests baseline, not the branch. Testing the branch requires the
branch to BE the installed plugin + a session restart (agent defs load at start).

**Decision (informed):** merge Phase 2a to main FIRST, then test on the updated plugin —
acceptable because layers 1-3 de-risked the loader mechanism and a failed test is a cheap
`git revert`. Version bumped 0.1.21 → **0.1.22** so re-install refreshes the cache.

Runbook (post-merge, capable session):
1. **Cleanup** other-session leftovers: kill stray gstable/wbft-node, `rm -rf /tmp/node-data`,
   restore `test/pr-77` to clean base `0bf2f4d1b`, delete `fix/LOCAL-*` throwaway branches.
2. **Update plugin** to 0.1.22 (re-install from main) and **restart the session**.
3. **Confirm active = branch**: `grep -l domain-pack ~/.claude/plugins/cache/coding-agent/
   coding-agent/0.1.22/agents/analyzer.md` (and NO `stablenet-context`).
4. **Run** the branch pipeline on PR-77 (`bench/fixtures/tickets/STABLE-0005.json`), isolated
   worktree at the indexed `base_commit`.
5. **Compare vs the PR-77 oracle** (root cause `eth/gasprice/anzeon.go:54 SetCurrentBlock` +
   `bench/fixtures/pr77/expert-fix.diff`) — the oracle is the recorded baseline-equivalent, so
   reaching it = no-regression. One run, no baseline re-run needed.
6. **Cleanup** (restore baseline, remove throwaway branch).
7. **If it regresses:** `git revert` the merge on main; reopen the branch for fixes.

## ✅ Layer 4 — RESULT (executed 2026-06-23)

Ran the Phase 2a analyzer on PR-77 on a clean checkout (`test/dev-test/pr-77` @0bf2f4d1b,
pr-77 cks serviceable; used the separate clean tree, not the contaminated `test/pr-77`).

- **Analysis no-regression: PASS.** Reached the PRIMARY oracle root cause
  `eth/gasprice/anzeon.go:54 SetCurrentBlock` (+ the secondary `anzeonTipCap` / `RemotesBelowTip`
  staleness) and confirmed RED (`TestReproduce_STABLE0005_...`). Matches the 06-22 baseline
  analyzer (#1 exact). The domain-pack loader resolved + classified (txpool/miner/...) correctly.
- **Real bug found by the live run:** the loader's `plugin/domains/...` path does not resolve for
  an installed plugin (subagent cwd is the target repo; the cache has no `plugin/` prefix). The
  analyzer worked around it by locating the dir, so analysis still passed — but the path was wrong.
- **Fixed:** `${CLAUDE_PLUGIN_ROOT}/domains/...` (PR #17, merged; current main 0.1.25).
- **Substitution verified live (0.1.25 installed + reloaded):** an agent loading the domain-pack
  skill sees the plugin-root token replaced inline with the absolute path
  (`/Users/.../0.1.25/domains/{project_id}/...`); `{project_id}` stays a runtime token. The loader
  now reads the correct absolute pack path with no workaround — the ADR §3.1 reliability caveat is
  empirically resolved.

**Conclusion:** Phase 2a (domain-pack wiring) + the path fix are verified clean. Remaining for P1:
Phase 2b (evaluator `go_stablenet_root` / `verification_stages` generalization) and Phase 3 (full
grep-clean acceptance).
