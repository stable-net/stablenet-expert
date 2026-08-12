#!/usr/bin/env bash
# check-environment.sh — common toolchain prerequisites for the stablenet-expert ecosystem
# as a whole. Deliberately NOT broken down per plugin: this is the same flat list as
# docs/SETUP.md §1 "Prerequisites" (Go/C toolchain/Node/git/gh/python3), checked unconditionally
# regardless of which plugins are actually installed. Doctor Step 0.
#
# The bar for belonging here is "every install needs it". A dependency of *building* an
# artefact does not qualify, however central the artefact is -- see the Ollama note below.
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

# Ollama + bge-m3 is deliberately not checked here. It is a build-side dependency: it embeds the
# corpus when the stablenet-knowledge index is *produced*. A machine that only queries the server
# never runs an embedder, so on every consumer -- which is nearly every install -- the check
# reported a warning about a tool that machine has no reason to have, and dropped ALL_PASS with
# it. Prerequisites for building the index live in docs/SETUP.md §4.3, next to the build steps
# that need them.

# Security policy -- the org's rules, loaded into every session through the user's CLAUDE.md.
# Not shipped by this marketplace: it is organisation policy, so doctor checks and points, and
# never writes it. Two failures are separated on purpose. A missing file is obvious once named;
# a file that exists but is not imported is the dangerous one, because everything looks
# installed while nothing is loaded -- the rules are simply absent from the session and no one
# has a reason to suspect it.
#
# Case is not part of the policy. The filename was hardcoded as SECURITY.md on both tests, and
# the import test was the only case-sensitive one -- so on macOS, whose filesystem is
# case-insensitive, `[ -f .../SECURITY.md ]` matched a lowercase security.md and passed while the
# grep for `@rules/SECURITY.md` failed against the `@rules/security.md` that was importing that
# very file. The result told a correctly-configured user their policy was "on disk but absent
# from every session", and the fix it printed would have imported the same file a second time.
# Both spellings are looked for now, and the import match is case-insensitive.
claude_md="$HOME/.claude/CLAUDE.md"
# Globbed rather than tested against a list of spellings, so the name reported back is the
# directory's own entry. Testing candidates would echo the spelling we guessed, which on a
# case-insensitive filesystem is not necessarily the one on disk.
security_rules=""
for candidate in "$HOME"/.claude/rules/[Ss][Ee][Cc][Uu][Rr][Ii][Tt][Yy].md; do
  if [ -f "$candidate" ]; then security_rules="$candidate"; break; fi
done
if [ -z "$security_rules" ]; then
  emit "Security rules" "critical" \
    "~/.claude/rules/SECURITY.md not found -- the group security policy is not installed. Get it from your security team and place it there, then add '@rules/SECURITY.md' to ~/.claude/CLAUDE.md"
  all_pass=false
elif [ ! -f "$claude_md" ]; then
  emit "Security rules" "critical" \
    "$(basename "$security_rules") is present but ~/.claude/CLAUDE.md does not exist, so nothing loads it -- create it with a line reading '@rules/SECURITY.md'"
  all_pass=false
elif ! grep -qiE '^[[:space:]]*@(rules/|~/\.claude/rules/|\$HOME/\.claude/rules/)SECURITY\.md[[:space:]]*$' "$claude_md"; then
  emit "Security rules" "critical" \
    "$(basename "$security_rules") exists but ~/.claude/CLAUDE.md does not import it -- add a line reading '@rules/SECURITY.md'. Until then the policy is on disk but absent from every session"
  all_pass=false
else
  emit "Security rules" "pass" "~/.claude/rules/$(basename "$security_rules") imported by ~/.claude/CLAUDE.md"
fi

if $all_pass; then
  emit "ALL_ENVIRONMENT_PASS" "pass" "all common ecosystem prerequisites present"
fi
