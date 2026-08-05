#!/usr/bin/env bash
# install-python.sh — install a Python interpreter new enough for this repository's test suite,
# without disturbing the interpreter the rest of the machine uses.
#
# Bash only, on purpose. This is the one repair step that cannot assume Python exists: doctor's
# Step 4 delegation runs `python3 <plugin>/scripts/setup.py` (ADR-0014), so on a machine with no
# interpreter the whole repair mechanism is unavailable until this script has run.
#
# What it does NOT do: it never edits PATH, never relinks `python3`, and never touches a shell
# profile. The installed interpreter is reached by absolute path through the
# STABLENET_EXPERT_PYTHON setting instead (ADR-0015), so nothing outside this repository's own
# hooks and scripts changes behaviour. There is consequently nothing to undo afterwards.
#
# Usage:
#   install-python.sh --check     report what would happen; installs nothing; always exits 0
#   install-python.sh --install   perform the install
#
# On success the final stdout line is `INTERPRETER=<absolute path>`, which the caller records as
# STABLENET_EXPERT_PYTHON.
set -u

TARGET_VERSION="3.12"   # matches .github/workflows/ci.yml
FLOOR_VERSION="3.10"    # below this the test suite cannot run (`dict | None` evaluated at runtime)

usage() {
  printf 'usage: %s (--check | --install)\n' "$(basename "$0")" >&2
  exit 2
}

# version_ge A B -> success (0) if version A >= version B
version_ge() {
  [ "$1" = "$2" ] && return 0
  [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n1)" = "$2" ]
}

interpreter_version() {
  "$1" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null
}

# Print the path of an already-installed interpreter that meets FLOOR_VERSION, if there is one.
# Searched newest-first so a machine with several versions yields the best available.
find_existing_interpreter() {
  local candidate resolved version
  for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    resolved="$(command -v "$candidate" 2>/dev/null)" || continue
    version="$(interpreter_version "$resolved")" || continue
    [ -n "$version" ] || continue
    if version_ge "$version" "$FLOOR_VERSION"; then
      printf '%s' "$resolved"
      return 0
    fi
  done
  return 1
}

# Which install channel applies on this machine. Homebrew is preferred when present: it is already
# trusted on the host and needs no remote script execution. uv is the fallback because it installs
# a standalone interpreter into the user's home directory without sudo.
choose_channel() {
  if command -v brew >/dev/null 2>&1; then
    printf 'brew'
  else
    printf 'uv'
  fi
}

describe_channel() {
  case "$1" in
    brew) printf 'brew install python@%s' "$TARGET_VERSION" ;;
    uv)
      if command -v uv >/dev/null 2>&1; then
        printf 'uv python install %s' "$TARGET_VERSION"
      else
        printf 'curl -LsSf https://astral.sh/uv/install.sh | sh   (installs uv into ~/.local/bin, no sudo)\n  then: uv python install %s' "$TARGET_VERSION"
      fi
      ;;
  esac
}

install_via_brew() {
  brew install "python@$TARGET_VERSION" >&2 || return 1
  # Homebrew deliberately does not relink `python3`; it exposes the versioned name only, which is
  # exactly the isolation this script wants.
  local prefix
  prefix="$(brew --prefix 2>/dev/null)" || return 1
  local path="$prefix/bin/python$TARGET_VERSION"
  [ -x "$path" ] && printf '%s' "$path"
}

install_via_uv() {
  if ! command -v uv >/dev/null 2>&1; then
    printf 'Installing uv (user-scoped, no sudo)...\n' >&2
    curl -LsSf https://astral.sh/uv/install.sh | sh >&2 || return 1
    # uv lands in ~/.local/bin; add it for this process only, not for the user's shell.
    PATH="$HOME/.local/bin:$PATH"
    export PATH
  fi
  command -v uv >/dev/null 2>&1 || return 1
  uv python install "$TARGET_VERSION" >&2 || return 1

  # Resolve the installed interpreter. `uv python find` is the documented way; the glob is a
  # fallback so a change in uv's CLI surface degrades to a slower lookup instead of a failure.
  local path
  path="$(uv python find "$TARGET_VERSION" 2>/dev/null)"
  if [ -n "$path" ] && [ -x "$path" ]; then
    printf '%s' "$path"
    return 0
  fi
  for path in "$HOME"/.local/share/uv/python/*"$TARGET_VERSION"*/bin/"python$TARGET_VERSION"; do
    [ -x "$path" ] && { printf '%s' "$path"; return 0; }
  done
  return 1
}

mode="${1:-}"
[ "$mode" = "--check" ] || [ "$mode" = "--install" ] || usage

existing="$(find_existing_interpreter)" && {
  printf 'Python %s already available, no install needed.\n' "$(interpreter_version "$existing")"
  printf 'INTERPRETER=%s\n' "$existing"
  exit 0
}

channel="$(choose_channel)"

if [ "$mode" = "--check" ]; then
  printf 'No interpreter >= %s found. Would install Python %s via %s:\n\n  %s\n\n' \
    "$FLOOR_VERSION" "$TARGET_VERSION" "$channel" "$(describe_channel "$channel")"
  printf 'Your existing python3 (%s) is left untouched; PATH is not modified.\n' \
    "$(command -v python3 2>/dev/null || printf 'none')"
  exit 0
fi

case "$channel" in
  brew) installed="$(install_via_brew)" ;;
  uv)   installed="$(install_via_uv)" ;;
esac

if [ -z "${installed:-}" ] || [ ! -x "$installed" ]; then
  printf 'Install failed. Run the command yourself and re-run doctor:\n\n  %s\n' \
    "$(describe_channel "$channel")" >&2
  exit 1
fi

printf 'Installed Python %s at %s\n' "$(interpreter_version "$installed")" "$installed"
printf 'INTERPRETER=%s\n' "$installed"
