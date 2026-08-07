#!/usr/bin/env bash
# check-environment.sh — common toolchain prerequisites for the stablenet-expert ecosystem
# as a whole. Deliberately NOT broken down per plugin: this is the same flat list as
# docs/SETUP.md §1 "Prerequisites" (Go/C toolchain/Node/git/gh/python3/Ollama+bge-m3), checked
# unconditionally regardless of which plugins are actually installed. Doctor Step 0.
set -u

emit() {
  local name="$1" status="$2" detail="$3"
  detail="$(printf '%s' "$detail" | tr '\n' ';' | sed 's/  */ /g; s/; */; /g; s/; $//')"
  printf '%s | %s | %s\n' "$name" "$status" "$detail"
}

# version_ge A B -> success (0) if version A >= version B
version_ge() {
  [ "$1" = "$2" ] && return 0
  [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n1)" = "$2" ]
}

all_pass=true

# Go >= 1.25 -- sibling stablenet-knowledge-mcp/chainbench Go wire
if command -v go >/dev/null 2>&1; then
  go_version="$(go version | grep -oE 'go[0-9]+\.[0-9]+(\.[0-9]+)?' | head -n1 | sed 's/^go//')"
  if [ -n "$go_version" ] && version_ge "$go_version" "1.25"; then
    emit "Go" "pass" "go$go_version"
  else
    emit "Go" "warn" "go${go_version:-?} found, need >= 1.25 (core-dev/contract-dev builds)"
    all_pass=false
  fi
else
  emit "Go" "critical" "not found -- required to build/test core-dev and contract-dev"
  all_pass=false
fi

# C toolchain (cc/clang) -- stablenet-knowledge links sqlite-vec via CGO
if command -v cc >/dev/null 2>&1 || command -v clang >/dev/null 2>&1; then
  emit "C toolchain" "pass" "$(command -v cc || command -v clang)"
else
  emit "C toolchain" "warn" "no cc/clang -- stablenet-knowledge (CGO/sqlite-vec) will fail to build"
  all_pass=false
fi

# Node is deliberately NOT checked. It was required when chainbench's MCP server was
# TypeScript; that server is a Go binary now (chainbench's Makefile builds it with `go build`),
# and no repository in this ecosystem carries a package.json. Reporting a missing Node told
# users to install something nothing uses.

# git >= 2.40 -- branch/commit/log throughout the pipeline
if command -v git >/dev/null 2>&1; then
  git_version="$(git --version | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -n1)"
  if [ -n "$git_version" ] && version_ge "$git_version" "2.40"; then
    emit "git" "pass" "$git_version"
  else
    emit "git" "warn" "${git_version:-?} found, need >= 2.40"
    all_pass=false
  fi
else
  emit "git" "critical" "not found -- required throughout the pipeline"
  all_pass=false
fi

# GitHub CLI (gh) >= 2.50, authenticated -- PR creation, comments, status checks, merge
if command -v gh >/dev/null 2>&1; then
  gh_version="$(gh --version | head -n1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?')"
  if gh auth status >/dev/null 2>&1; then
    gh_auth_state="authenticated"
  else
    gh_auth_state="NOT authenticated -- run 'gh auth login'"
  fi
  if [ -n "$gh_version" ] && version_ge "$gh_version" "2.50"; then
    emit "GitHub CLI" "pass" "$gh_version, $gh_auth_state"
  else
    emit "GitHub CLI" "warn" "${gh_version:-?} found, need >= 2.50; $gh_auth_state"
    all_pass=false
  fi
else
  emit "GitHub CLI" "critical" "not found -- required for PR creation/review/merge"
  all_pass=false
fi

# python3 -- load-bearing in a way the other entries are not. Doctor's own Step 4 delegation runs
# `python3 <plugin>/scripts/setup.py` (ADR-0014), so without an interpreter doctor cannot set up
# ANY plugin it installs -- the repair mechanism itself is gone, not just one feature. Hence
# `critical` when absent, and hence install-python.sh is bash-only.
#
# The supported version is 3.12 and nothing older (ADR-0015). 3.9 was considered as a floor --
# macOS still ships it -- and rejected: it is end-of-life upstream and Homebrew disables its
# formula on 2026-10-15, so a floor there would mean testing only on an unsupported runtime and
# would stop being installable within weeks.
#
# Below 3.12 is reported but never blocks: doctor offers the install, it does not demand it.
python_supported="3.12"    # what install-python.sh installs; also .github/workflows/ci.yml
if command -v "${STABLENET_EXPERT_PYTHON:-python3}" >/dev/null 2>&1; then
  python_version="$("${STABLENET_EXPERT_PYTHON:-python3}" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)"
  if [ -z "$python_version" ]; then
    emit "python3" "warn" "found on PATH but 'python3 -c' failed -- the interpreter looks broken"
    all_pass=false
  elif version_ge "$python_version" "$python_supported"; then
    emit "python3" "pass" "$python_version"
  else
    emit "python3" "warn" \
      "$python_version -- this marketplace supports >= $python_supported. Run scripts/install-python.sh to install it alongside; your system python3 and PATH are left untouched (the path is recorded as STABLENET_EXPERT_PYTHON)"
    all_pass=false
  fi
else
  emit "python3" "critical" \
    "not found -- doctor cannot run any plugin's setup.py without it (ADR-0014). Install with scripts/install-python.sh (installs $python_supported)"
  all_pass=false
fi

# Ollama + bge-m3 -- stablenet-knowledge semantic + intent retrieval (degrades gracefully without it)
if command -v ollama >/dev/null 2>&1; then
  if ollama list 2>/dev/null | grep -q "bge-m3"; then
    emit "Ollama" "pass" "running, bge-m3 pulled"
  else
    emit "Ollama" "warn" "installed but bge-m3 not pulled -- run 'ollama pull bge-m3' (see docs/SETUP.md §1)"
    all_pass=false
  fi
else
  emit "Ollama" "warn" "not found -- stablenet-knowledge falls back to degraded (keyword-only) retrieval, see docs/SETUP.md §1"
  all_pass=false
fi

if $all_pass; then
  emit "ALL_ENVIRONMENT_PASS" "pass" "all common ecosystem prerequisites present"
fi
