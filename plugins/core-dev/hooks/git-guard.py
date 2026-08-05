#!/usr/bin/env python3
"""Git-safety PreToolUse guard (core-dev plugin).

Turns the prose git-safety rules (no direct commit/push to the default branch,
no force-push, push/merge only when asked) into a deterministic hook the model
cannot forget — the fail-closed gate that makes autonomy=auto safe to enable.
Generic across repos.

Decisions (PreToolUse on Bash):
  deny  — force-push; push to a protected branch (main/master); commit while the
          working tree is on a protected branch.
  ask   — destructive history/tree ops (reset --hard, clean -f[d], branch -D) and
          tag / release pushes (relaxed to allow only when the active workspace
          has autonomy.auto_merge == true).
  (allow) — anything else, OR any parse failure: the guard fires ONLY on a
            positively-matched dangerous pattern, never on uncertainty about an
            unrelated command, so it can't break normal work.

Communicates via JSON on stdout (permissionDecision). Branch-dependent checks run
git in the hook's cwd; an explicit `git -C <other-repo>` skips the cwd branch
check (the target tree is unknown to the hook).
"""
import sys
import json
import re
import os
import glob
import subprocess

PROTECTED = ("main", "master")


def emit(decision, reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))


def _git(args, cwd=None):
    try:
        out = subprocess.run(["git"] + args, capture_output=True, text=True,
                             timeout=2, cwd=cwd)
        return out.stdout.strip()
    except Exception:
        return ""


def _effective_cwd(cmd):
    """Directory the git invocation in `cmd` will actually run in.

    A command like `cd /some/worktree && git commit ...` runs git somewhere other than this
    hook's own cwd. Reading the branch from the hook's cwd was wrong in both directions: it
    denied legitimate commits made in a feature worktree from a checkout sitting on main, and
    it let a commit onto main slip through whenever the hook's own cwd happened to be on a
    feature branch. Honour a leading `cd` so the guard judges the tree git will really touch.

    Only a `cd` that precedes the git call is considered, and only a literal path -- anything
    with substitution or globbing is left alone and the hook falls back to its own cwd, which
    is the conservative direction (it still checks *a* repository rather than skipping).
    """
    # Cut at the git *command*, not at the substring "git" -- a path like
    # /Users/me/Work/github/repo contains it and would truncate mid-path.
    git_at = re.search(r'(^|[;&|])\s*git(\s|$)', cmd)
    head = cmd[:git_at.start()] if git_at else cmd
    match = None
    for match in re.finditer(r'(?:^|[;&|]\s*)cd\s+([^;&|]+?)\s*(?=[;&|]|$)', head):
        pass          # keep the last cd before git -- later ones win
    if not match:
        return None
    path = match.group(1).strip().strip('"').strip("'")
    if not path or any(ch in path for ch in "$`*?~"):
        return None
    return path if os.path.isdir(path) else None


def _workspaces():
    """All parseable pipeline workspaces' state.json under the cwd repo root."""
    root = _git(["rev-parse", "--show-toplevel"]) or os.getcwd()
    out = []
    for p in glob.glob(os.path.join(root, ".stablenet-expert", "tickets", "*", "state.json")):
        try:
            out.append(json.load(open(p, encoding="utf-8")))
        except Exception:
            continue
    return out


def _auto_merge_enabled():
    """True if any recent active workspace opted into auto_merge (relaxes tag push)."""
    for st in _workspaces():
        if ((st.get("config") or {}).get("autonomy") or {}).get("auto_merge") is True:
            return True
    return False


_TERMINAL = {"COMPLETION", "COMPLETED", "BLOCKED"}


def _active_base_guards():
    """(ticket branches, base refs, latest_policy) of in-flight workspaces.

    In-flight = current_state is non-terminal. These are the tickets whose base
    must not be moved by a branch switch or a pull (implementer §3.1: the base
    is the HEAD recorded at intake, NOT the latest default branch).
    """
    branches, bases, latest = set(), set(), False
    for st in _workspaces():
        if (st.get("current_state") or "") in _TERMINAL or not st.get("current_state"):
            continue
        cfg = st.get("config") or {}
        b = ((st.get("states") or {}).get("IMPLEMENTATION") or {}).get("branch")
        if b:
            branches.add(b)
        if cfg.get("base_ref"):
            bases.add(cfg["base_ref"])
        if cfg.get("base_policy") == "latest":
            latest = True
    return branches, bases, latest


def _checkout_target(cmd):
    """(verb, target) of a `git checkout|switch` — target '--' = file restore,
    '-b' = branch creation, else the first non-option token (branch/sha), or None."""
    m = re.search(r'\bgit\b[^;&|]*\b(checkout|switch)\b([^;&|]*)', cmd)
    if not m:
        return None, None
    rest = m.group(2)
    if re.match(r'\s+--(\s|$)', rest):
        return m.group(1), "--"
    for tok in rest.split():
        if tok in ("-b", "-B", "-c", "-C"):
            return m.group(1), "-b"
        if tok == "--":
            return m.group(1), "--"
        if tok.startswith("-"):
            continue
        return m.group(1), tok
    return m.group(1), None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if data.get("tool_name") != "Bash":
        return 0
    cmd = ((data.get("tool_input") or {}).get("command") or "")
    # Only inspect commands that actually invoke git (at start or after a separator).
    if not cmd or not re.search(r'(^|[;&|])\s*git(\s|$)', cmd):
        return 0

    is_push = re.search(r'\bgit\b[^;&|]*\bpush\b', cmd) is not None

    # --- deny: force-push (rewrites shared history) ---
    if is_push and re.search(r'(--force(?!-with-lease)\b|(^|\s)-f(\s|$))', cmd):
        emit("deny",
             "Force-push is blocked — it rewrites shared history. If a force-push is "
             "genuinely required, run it yourself outside the agent.")
        return 0

    # --- deny: push to a protected branch ---
    if is_push and re.search(r'\bpush\b[^;&|]*(?:\s|:)(?:main|master)(?:\s|:|$)', cmd):
        emit("deny",
             "Direct push to a protected branch (main/master) is blocked. Push a feature "
             "branch and open a PR; merge to the default branch happens via review.")
        return 0

    # --- deny: commit while ON a protected branch (the tree git will actually touch; -C skips) ---
    if re.search(r'\bgit\b[^;&|]*\bcommit\b', cmd) and not re.search(r'\bgit\s+-C\b', cmd):
        target_dir = _effective_cwd(cmd)
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=target_dir)
        if branch in PROTECTED:
            where = f" in {target_dir}" if target_dir else ""
            emit("deny",
                 f"Committing directly on '{branch}'{where} is blocked. Create a feature branch "
                 f"first (git checkout -b <branch>) and commit there.")
            return 0

    # --- ask: base-moving ops while a pipeline ticket is in flight ---
    # The ticket's base is the HEAD recorded at intake (state.config.base_ref).
    # Switching to another named branch or pulling would silently change the code
    # under the ticket (e.g. jump a pinned pre-fix commit to the latest default
    # branch). Allowed without asking: branch creation (-b/-c), file restore
    # (checkout -- <path>), detached checkouts of commit hashes / HEAD-relative
    # refs (evaluator's red-check), and the ticket's own branch / base_ref.
    verb, target = _checkout_target(cmd)
    is_pull = re.search(r'\bgit\b[^;&|]*\bpull\b', cmd) is not None
    if (verb and target not in (None, "--", "-b")) or is_pull:
        branches, bases, latest_ok = _active_base_guards()
        if (branches or bases) and not latest_ok:
            if is_pull:
                emit("ask", "A pipeline ticket is in flight and its base is pinned "
                            "(state.config.base_ref). `git pull` would move the working "
                            "tree past that base. Confirm, or set base_policy=\"latest\" "
                            "if syncing is intended.")
                return 0
            allowed = (
                target in branches
                or target in bases
                or any(b.startswith(target) for b in bases)   # abbreviated sha of base_ref
                or re.fullmatch(r'[0-9a-f]{7,40}', target) is not None  # detached commit (red-check)
                or target == "HEAD" or target.startswith("HEAD~") or target.startswith("HEAD^")
            )
            if not allowed:
                emit("ask", f"A pipeline ticket is in flight and its base is pinned. "
                            f"`git {verb} {target}` switches to another branch, which changes "
                            f"the base code under the ticket. Work stays on the ticket branch "
                            f"created from state.config.base_ref (implementer §3.1). Confirm "
                            f"only if you intend to abandon that base.")
                return 0

    # --- ask: destructive history/tree ops ---
    if re.search(r'\breset\b[^;&|]*--hard', cmd):
        emit("ask", "`git reset --hard` discards uncommitted work and rewrites the branch "
                    "tip. Confirm this is intended.")
        return 0
    if re.search(r'\bclean\b\s+-[a-z]*f', cmd):
        emit("ask", "`git clean -f` permanently deletes untracked files. Confirm the target "
                    "and that nothing valuable is untracked.")
        return 0
    if re.search(r'\bbranch\b[^;&|]*\s-D\b', cmd):
        emit("ask", "`git branch -D` force-deletes a branch (even unmerged). Confirm it is "
                    "merged or disposable.")
        return 0

    # --- ask: tag / release push (relaxed when auto_merge is enabled) ---
    if is_push and re.search(r'(--tags\b|\btag\b)', cmd):
        if not _auto_merge_enabled():
            emit("ask", "Pushing tags publishes a release ref. Confirm the tag and target "
                        "(or enable autonomy.auto_merge for release automation).")
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
