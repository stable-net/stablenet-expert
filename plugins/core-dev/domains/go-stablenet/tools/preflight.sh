#!/usr/bin/env bash
# go-stablenet domain tool — build-toolchain preflight.
#
# Project-specific runtime script (domains/go-stablenet/tools/), routed by the
# domain-pack `tools` manifest and invoked as:
#     bash ${CLAUDE_PLUGIN_ROOT}/domains/go-stablenet/tools/preflight.sh [repo_root]
#
# Verifies the prerequisites this pack's verification.build ("make gstable") needs,
# so a missing toolchain fails fast with a clear message instead of deep inside a
# build. Grounded in the pack contract (make + the gstable target) — no assumption
# about project internals. Exit 0 = ready, non-zero = a listed prerequisite missing.
set -u
repo_root="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
missing=0

need() {  # need <cmd> <hint>
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'MISSING: %s — %s\n' "$1" "$2"
    missing=1
  fi
}

need go   "install Go (the pack builds with 'go' / 'make gstable')"
need make "install make (verification.build.binary_cmd = 'make gstable')"

if [ -f "${repo_root}/Makefile" ]; then
  if ! grep -qE '^gstable[[:space:]]*:' "${repo_root}/Makefile"; then
    printf 'WARN: Makefile present but no "gstable" target found in %s/Makefile\n' "${repo_root}"
  fi
else
  printf 'MISSING: %s/Makefile — the pack build target "gstable" needs it\n' "${repo_root}"
  missing=1
fi

if [ "${missing}" -eq 0 ]; then
  printf 'preflight OK: go + make present, Makefile at %s\n' "${repo_root}"
fi
exit "${missing}"
