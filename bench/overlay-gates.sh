#!/usr/bin/env bash
# overlay-gates.sh — run every stream-6 overlay regression gate in one shot.
#
# The overlay improvements (docs/coding-agent-overlay-improvements-and-eval-2026-06-22.md)
# each shipped a deterministic harness proving "before vs after". This bundles them so a
# later edit to an agent spec (or a model-pin drift) that silently breaks a contract is
# caught immediately rather than at the next live run. Each gate exits non-zero on
# regression; this script aggregates and exits non-zero if ANY gate fails.
#
# Wire as a pre-commit hook or CI step:
#   bash bench/overlay-gates.sh
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || { echo "cannot cd to repo root"; exit 2; }

fail=0
run() {  # run <label> <cmd...>
  local label="$1"; shift
  local out
  if out="$("$@" 2>&1)"; then
    printf '  PASS  %s\n' "$label"
  else
    printf '  FAIL  %s\n' "$label"
    printf '%s\n' "$out" | sed 's/^/          | /'
    fail=1
  fi
}

echo "# coding-agent overlay regression gates (stream-6)"
echo

echo "P0 — plan/write-site contract machine-checks"
run "P0 mutant-corpus score (after>before, no false-pos)" python3 bench/p0-mutants/score.py
run "P0 harness tests"                                     python3 bench/p0-mutants/tests/test_rules.py
echo
echo "P2 — stablenet-knowledge in-run retrieval discipline"
run "P2 stablenet-knowledge-fault score (silent-incomplete == 0)"          python3 bench/p2-cks-fault/score.py
run "P2 harness tests"                                     python3 bench/p2-cks-fault/tests/test_policy.py
echo
echo "P3 — single-source model pins"
run "P3 model-pins check (no drift)"                       python3 bench/model-pins/check.py
run "P3 model-pins tests"                                  python3 bench/model-pins/tests/test_check.py
echo
echo "P6 — single-source MCP tool-name namespace"
run "P6 mcp-namespace check (no drift)"                    python3 scripts/contract/sync-mcp-namespace.py
run "P6 mcp-namespace tests"                               python3 scripts/contract/tests/test_sync_mcp_namespace.py
echo
echo "P5 — scoped evaluator cleanup"
run "P5 cleanup-scope verify (foreign survives)"           bash bench/p5-cleanup-scope/verify.sh
echo
echo "P1 — domain-pack structure (Phase 1)"
run "P1 domain-pack structure check"                       python3 bench/domain-pack/check.py
run "P1 domain-pack tests"                                 python3 bench/domain-pack/tests/test_check.py
echo
echo "setup / doctor (env onboarding + remediation routing)"
run "setup tests (autonomous guard, repo_root_env)"       python3 plugins/core-dev/scripts/tests/test_setup.py
run "doctor tests (fix-table coverage, remediation)"      python3 plugins/core-dev/scripts/tests/test_doctor.py
run "resolve-project (domain-pack routing, no fallback)"  python3 plugins/core-dev/scripts/tests/test_resolve_project.py
echo
echo "safety hooks (git-guard / on-stop / session-context)"
run "hooks deterministic guards"                          python3 bench/hooks/test_hooks.py
echo
echo "bench measurement infra"
run "bench unit tests"                                     python3 -m unittest bench.tests.test_usage bench.tests.test_report

echo
if [ "$fail" -eq 0 ]; then
  echo "overlay-gates: ALL PASS"
else
  echo "overlay-gates: FAIL — a stream-6 contract regressed (see above)"
fi
exit "$fail"
