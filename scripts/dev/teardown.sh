#!/usr/bin/env bash
# teardown.sh — put this machine back to "nothing installed", for install/setup testing.
#
# DEVELOPMENT ONLY. This is not part of the marketplace and is not shipped in any plugin: it
# exists so the install -> doctor -> uninstall cycle can be run over and over while that flow is
# being built. A user removing the plugin for real wants `setup.py --uninstall` and the two
# `claude plugin uninstall` lines, not a script that also drops marketplaces and OAuth tokens.
#
# Order matters in two places, and neither is obvious:
#
#   1. setup.py --uninstall runs FIRST, while core-dev is still installed. Once the plugin is
#      gone so is the manifest that records which settings were ours, and no later step can
#      tell them from the ones you set by hand.
#   2. `claude mcp logout` runs BEFORE uninstalling the Atlassian plugin. Logout resolves the
#      server by name, and the name comes from the plugin's .mcp.json -- remove the plugin
#      first and logout fails with "No MCP server named ...", leaving the OAuth token behind.
#      A token left behind means the next test skips the authentication step entirely.
#
# Every step is allowed to fail. A teardown that stops because something was already absent is
# useless for the thing it exists for -- being run repeatedly, from any starting state.
#
# Usage:
#   scripts/dev/teardown.sh                    # show what would run
#   scripts/dev/teardown.sh --yes              # run it
#   scripts/dev/teardown.sh --yes --repo ~/x   # take settings back from a different project
set -uo pipefail

SELF_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SETUP="$SELF_REPO/plugins/core-dev/scripts/setup.py"

# Which project's settings to take back. Defaults to this checkout, which is right when you ran
# setup from here -- but run this script from a worktree and that default points at the
# worktree, not at the project you actually configured. Name it when they differ.
REPO="$SELF_REPO"
APPLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --yes)  APPLY=1; shift ;;
    --repo)
      # `set -e` is off on purpose (every teardown step may fail), so a bad cd here would
      # otherwise fall through and clean the wrong directory.
      REPO="$(cd "${2:?--repo needs a path}" 2>/dev/null && pwd)" || {
        echo "error: --repo $2 는 디렉터리가 아닙니다" >&2; exit 2; }
      shift 2 ;;
    *) echo "usage: $(basename "$0") [--yes] [--repo <설정을 되돌릴 프로젝트 경로>]" >&2; exit 2 ;;
  esac
done

step() {                                  # step <description> <command...>
  local desc="$1"; shift
  if [ "$APPLY" -eq 0 ]; then
    printf '  %s\n      %s\n' "$desc" "$*"
    return 0
  fi
  printf '\n=== %s\n' "$desc"
  "$@" 2>&1 | sed 's/^/    /'
  local rc=${PIPESTATUS[0]}
  [ "$rc" -eq 0 ] || printf '    (exit %s — 이미 없거나 해당 없음, 계속 진행)\n' "$rc"
}

if [ "$APPLY" -eq 0 ]; then
  echo "dry run — 아래를 실행합니다. 실제로 하려면 --yes 를 붙이세요."
  echo
fi

# 1. 우리가 쓴 설정 회수 — 반드시 플러그인 제거 전에.
step "설정 회수 — $REPO (core-dev 가 아직 있어야 함)" \
     python3 "$SETUP" --repo "$REPO" --uninstall --yes

# 2. 플러그인과 마켓플레이스.
step "core-dev 제거"            claude plugin uninstall core-dev@stablenet-expert
step "stablenet-expert 제거"    claude plugin uninstall stablenet-expert@stablenet-expert
step "stablenet-expert 마켓플레이스 제거" claude plugin marketplace remove stablenet-expert

# 3. Atlassian — 자격증명을 먼저 지운다.
step "Atlassian OAuth 자격증명 삭제 (플러그인 제거 전)" \
     claude mcp logout plugin:atlassian:atlassian
step "atlassian 제거"           claude plugin uninstall atlassian@claude-plugins-official
step "claude-plugins-official 마켓플레이스 제거" \
     claude plugin marketplace remove claude-plugins-official

if [ "$APPLY" -eq 1 ]; then
  printf '\n=== 남은 것 확인\n'
  claude plugin list 2>&1 | sed 's/^/    /'
  claude plugin marketplace list 2>&1 | grep "❯" | sed 's/^/    /' || echo "    마켓플레이스 없음"
  printf '\n설정은 --uninstall 이 기록한 것만 지웠습니다. 직접 넣은 env 는 그대로입니다:\n'
  python3 -c "
import json,pathlib
p = pathlib.Path.home()/'.claude/settings.json'
print('   ', list((json.load(open(p)).get('env') or {}).keys()) if p.exists() else '(settings.json 없음)')"
fi
