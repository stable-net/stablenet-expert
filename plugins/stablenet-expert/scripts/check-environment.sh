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

# Go >= 1.25 -- jira-gateway + sibling stablenet-knowledge-mcp/chainbench Go wire
if command -v go >/dev/null 2>&1; then
  gv="$(go version | grep -oE 'go[0-9]+\.[0-9]+(\.[0-9]+)?' | head -n1 | sed 's/^go//')"
  if [ -n "$gv" ] && version_ge "$gv" "1.25"; then
    emit "Go" "pass" "go$gv"
  else
    emit "Go" "warn" "go${gv:-?} found, need >= 1.25 (core-dev/contract-dev builds)"
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

# Node >= 18 + npm -- chainbench MCP server (TypeScript)
if command -v node >/dev/null 2>&1; then
  nv="$(node --version | sed 's/^v//')"
  if version_ge "$nv" "18.0.0"; then
    emit "Node" "pass" "v$nv"
  else
    emit "Node" "warn" "v$nv found, need >= 18 (chainbench MCP server)"
    all_pass=false
  fi
else
  emit "Node" "warn" "not found -- chainbench MCP server (TypeScript) will not run"
  all_pass=false
fi

# git >= 2.40 -- branch/commit/log throughout the pipeline
if command -v git >/dev/null 2>&1; then
  gitv="$(git --version | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -n1)"
  if [ -n "$gitv" ] && version_ge "$gitv" "2.40"; then
    emit "git" "pass" "$gitv"
  else
    emit "git" "warn" "${gitv:-?} found, need >= 2.40"
    all_pass=false
  fi
else
  emit "git" "critical" "not found -- required throughout the pipeline"
  all_pass=false
fi

# GitHub CLI (gh) >= 2.50, authenticated -- PR creation, comments, status checks, merge
if command -v gh >/dev/null 2>&1; then
  ghv="$(gh --version | head -n1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?')"
  if gh auth status >/dev/null 2>&1; then
    auth="authenticated"
  else
    auth="NOT authenticated -- run 'gh auth login'"
  fi
  if [ -n "$ghv" ] && version_ge "$ghv" "2.50"; then
    emit "GitHub CLI" "pass" "$ghv, $auth"
  else
    emit "GitHub CLI" "warn" "${ghv:-?} found, need >= 2.50; $auth"
    all_pass=false
  fi
else
  emit "GitHub CLI" "critical" "not found -- required for PR creation/review/merge"
  all_pass=false
fi

# python3 -- this plugin's own doctor checks (and the lint script) need it
if command -v python3 >/dev/null 2>&1; then
  emit "python3" "pass" "$(python3 --version 2>&1)"
else
  emit "python3" "critical" "not found -- stablenet-expert's own doctor checks require it"
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
