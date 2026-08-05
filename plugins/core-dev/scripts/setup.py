#!/usr/bin/env python3
"""setup.py — check and register the settings core-dev needs to run.

The plugin's MCP servers (.mcp.json) read their binary paths and secrets from
${VAR} substitutions, which Claude Code resolves from the session env. This
script makes those values present in the *project* settings so a freshly
installed plugin "just works":

  - public/path values  -> {repo_root}/.claude/settings.json        ("env" block)
  - secrets (API token) -> {repo_root}/.claude/settings.local.json  ("env" block)

Values are filled in this order: explicit --set, existing process env, then
auto-detection of sibling repos. Anything still missing is reported (use --fix
with --set, or --interactive to be prompted). settings.local.json is added to
.gitignore so the token is never committed.

Modes:
  --check        report status, exit 1 if any REQUIRED value is unresolved (default)
  --fix          write resolved values into the settings files (idempotent merge)
  --set K=V      provide a value explicitly (repeatable); wins over detection
  --interactive  prompt on stdin for any value still missing (human terminal use)
  --force        overwrite values already present in settings (default: keep them)

Stdlib only. Run from inside the project where you use core-dev.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# (key, where, description, how-to-find)
PUBLIC = "settings.json"
SECRET = "settings.local.json"

REQUIRED = [
    ("STABLENET_KNOWLEDGE_MCP_BIN", PUBLIC, "stablenet-knowledge MCP binary",
     "build the sibling stablenet-knowledge-mcp repo (see its README) -> bin/stablenet-knowledge-mcp"),
    ("STABLENET_KNOWLEDGE_CONFIG", PUBLIC, "stablenet-knowledge config yaml (ckg/ckv paths)",
     "sibling stablenet-knowledge-mcp repo's cks-stablenet.yaml or cks.yaml"),
    ("JIRA_GATEWAY_BIN", PUBLIC, "jira-gateway MCP binary",
     "build packages/jira-gateway-mcp in this repo (go build) -> bin/jira-gateway-mcp"),
    ("JIRA_BASE_URL", PUBLIC, "Jira site URL, e.g. https://your.atlassian.net",
     "your organization's Atlassian site URL"),
    ("JIRA_USER_EMAIL", PUBLIC, "Jira account email",
     "the email of the Atlassian account the API token below belongs to"),
    ("CHAINBENCH_DIR", PUBLIC, "chainbench checkout directory",
     "sibling chainbench repo's checkout path"),
    ("JIRA_API_TOKEN", SECRET, "Jira API token (secret)",
     "create one at https://id.atlassian.com/manage-profile/security/api-tokens"),
]

# --autonomous: granular permissions.allow (ADR §5.2) — the plugin's own MCP tools,
# read-only bash, and the pipeline's write path (file edits, build/test, feature-branch
# git). Destructive git stays out: force-push / protected-branch push / commit-on-main
# are DENIED and reset --hard / clean -f / tag push are ASKED by the git-guard hook
# regardless of this allowlist. Merge/tag/release (gh pr merge, git tag) are also
# intentionally NOT allowed here — they stay behind /core-dev:merge and its gates.
AUTONOMOUS_ALLOW = [
    "mcp__plugin_core-dev_stablenet-knowledge__*",
    "mcp__plugin_core-dev_chainbench__*",
    "mcp__plugin_core-dev_jira-gateway__*",
    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)",
    "Bash(git rev-parse:*)", "Bash(git show:*)", "Bash(git branch:*)",
    "Bash(ls:*)", "Bash(cat:*)", "Bash(grep:*)", "Bash(rg:*)", "Bash(find:*)",
    # pipeline write path (implementer/evaluator): file edits + workspace dirs
    "Write", "Edit",
    "Bash(mkdir:*)", "Bash(date:*)", "Bash(python3:*)",
    # build & verify
    "Bash(go build:*)", "Bash(go test:*)", "Bash(go vet:*)",
    "Bash(gofmt:*)", "Bash(golangci-lint:*)", "Bash(make:*)",
    # feature-branch git (guard hook still denies protected-branch/destructive ops)
    "Bash(git add:*)", "Bash(git commit:*)", "Bash(git checkout:*)",
    "Bash(git switch:*)", "Bash(git restore --staged:*)", "Bash(git push:*)",
    # PR creation/inspection only — merge stays with /core-dev:merge
    "Bash(gh pr create:*)", "Bash(gh pr view:*)", "Bash(gh pr list:*)",
    "Bash(gh pr checks:*)",
]

# --autonomous also registers permissions.deny: secret files the agent must never
# read via the Read tool, even while the allowlist above is active (defense-in-depth;
# mirrors gsd-core's installer denies). settings.local.json holds JIRA_API_TOKEN.
AUTONOMOUS_DENY = [
    "Read(.env)",
    "Read(.env.*)",
    "Read(.secrets)",
    "Read(.claude/settings.local.json)",
]


def _repo_root() -> Path:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True)
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def _first_existing(*paths: Path) -> str | None:
    for p in paths:
        if p and p.exists():
            return str(p)
    return None


def _detect(repo_root: Path) -> dict[str, str]:
    """Best-effort auto-detection of path-style values from sibling repos."""
    base = repo_root.parent  # e.g. .../github/, sibling to code-knowledge-system
    cks = base / "code-knowledge-system"
    se = base / "stablenet-expert"
    found: dict[str, str] = {}

    v = _first_existing(cks / "bin" / "stablenet-knowledge-mcp")
    if v:
        found["STABLENET_KNOWLEDGE_MCP_BIN"] = v
    # stablenet-knowledge config: prefer a stablenet-scoped config, else a generic cks.yaml
    if cks.is_dir():
        for name in ("cks-stablenet.yaml", "cks.yaml"):
            v = _first_existing(cks / name)
            if v:
                found["STABLENET_KNOWLEDGE_CONFIG"] = v
                break
    v = _first_existing(se / "packages" / "jira-gateway-mcp" / "bin" / "jira-gateway-mcp",
                        repo_root / "packages" / "jira-gateway-mcp" / "bin" / "jira-gateway-mcp")
    if v:
        found["JIRA_GATEWAY_BIN"] = v
    v = _first_existing(base / "chainbench")
    if v:
        found["CHAINBENCH_DIR"] = v
    return found


PLACEHOLDER_RE = re.compile(r"^CHANGE-ME", re.IGNORECASE)


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _persisted(claude_dir: Path) -> dict[str, tuple[str, str]]:
    """Currently-persisted, non-placeholder env values -> {key: (value, scope)}.

    Checks project scope first (claude_dir/settings.json, settings.local.json), then falls back
    to the global user-scope ~/.claude/settings.json -- matching Claude Code's own scope
    precedence (local > project > user), and matching what check-mcp-connectivity.sh actually
    reads (the global file) for plugins installed with --scope user. This is READ-ONLY: --fix
    below never writes to the global file, only to claude_dir's own settings.json/
    settings.local.json -- extending *detection* to the global scope closes the false "all
    resolved" report a project-scope-only check gave while a value only existed globally (or,
    worse, while a process env var happened to shadow a real placeholder sitting in either
    file); it does not change what gets written.

    A key present with a literal CHANGE-ME-... placeholder is treated as NOT persisted (not a
    usable value even though the key technically exists) at either scope.
    """
    found: dict[str, tuple[str, str]] = {}
    for name in ("settings.json", "settings.local.json"):
        env = _load_json(claude_dir / name).get("env")
        if not isinstance(env, dict):
            continue
        for k, v in env.items():
            if v and not PLACEHOLDER_RE.match(v) and k not in found:
                found[k] = (v, "project")
    global_env = _load_json(Path.home() / ".claude" / "settings.json").get("env")
    if isinstance(global_env, dict):
        for k, v in global_env.items():
            if v and not PLACEHOLDER_RE.match(v) and k not in found:
                found[k] = (v, "global")
    return found


def _resolve(key: str, overrides: dict[str, str], persisted: dict[str, tuple[str, str]],
             detected: dict[str, str]) -> tuple[str | None, str]:
    """Return (value, source). source in {set, project, global, env, detected, none}.

    A persisted value (project or global scope) outranks the raw process environment: it's what
    Claude Code's MCP servers actually read via ${VAR} substitution, whereas a process env var
    can be an unrelated shell-profile export that Claude Code never sees -- treating it as
    "resolved" would silently disagree with what check-mcp-connectivity.sh reports for the exact
    same key.
    """
    if key in overrides:
        return overrides[key], "set"
    if key in persisted:
        value, scope = persisted[key]
        return value, scope
    if os.environ.get(key):
        return os.environ[key], "env"
    if key in detected:
        return detected[key], "detected"
    return None, "none"


def _merge_env(path: Path, values: dict[str, str], force: bool) -> list[str]:
    """Merge values into the "env" block of a settings file. Returns keys written.

    A CHANGE-ME-... placeholder already sitting in this key is always replaced (even without
    --force) -- it's an explicit "not configured yet" marker, not a real value someone set on
    purpose, so it doesn't get the same "keep existing" protection a genuine value gets.
    """
    doc = _load_json(path)
    env = doc.get("env")
    if not isinstance(env, dict):
        env = {}
    written = []
    for k, v in values.items():
        if not v:
            continue
        existing = env.get(k)
        if existing and not force and not PLACEHOLDER_RE.match(existing):
            continue  # keep existing genuine value
        env[k] = v
        written.append(k)
    doc["env"] = env
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return written


def _plugin_root() -> Path:
    """The installed plugin root (scripts/ lives directly under it)."""
    return Path(__file__).resolve().parent.parent


def _repo_root_env(plugin_root: Path, repo_root: Path, override: str | None) -> str | None:
    """Active domain pack's verification.repo_root_env name (e.g. GO_STABLENET_ROOT).

    project_id: --project override > single pack > repo-name match (mirrors doctor.py).
    """
    domains = plugin_root / "domains"
    packs = sorted(d.name for d in domains.glob("*")
                   if (d / "domain-pack.json").is_file()) if domains.is_dir() else []
    pid = override or (packs[0] if len(packs) == 1 else None)
    if not pid:
        base = repo_root.name
        pid = next((p for p in packs if p and p in base), None)
    if not pid:
        return None
    pack = _load_json(plugin_root / "domains" / pid / "domain-pack.json")
    return (pack.get("verification") or {}).get("repo_root_env")


def _merge_perms(path: Path, key: str, entries: list[str]) -> list[str]:
    """Merge entries into permissions.<key> (dedup). Returns newly-added entries."""
    doc = _load_json(path)
    perms = doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {}
    lst = perms.get(key) if isinstance(perms.get(key), list) else []
    added = [e for e in entries if e not in lst]
    lst.extend(added)
    perms[key] = lst
    doc["permissions"] = perms
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return added


def _merge_allow(path: Path, entries: list[str]) -> list[str]:
    return _merge_perms(path, "allow", entries)


def _merge_deny(path: Path, entries: list[str]) -> list[str]:
    return _merge_perms(path, "deny", entries)


def _ensure_gitignored(repo_root: Path, rel: str) -> None:
    gi = repo_root / ".gitignore"
    line = rel
    existing = gi.read_text().splitlines() if gi.is_file() else []
    if line in existing:
        return
    with gi.open("a") as fh:
        if existing and existing[-1] != "":
            fh.write("\n")
        fh.write(f"# core-dev local secrets\n{line}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check/register core-dev settings")
    ap.add_argument("--check", action="store_true", help="report only (default)")
    ap.add_argument("--fix", action="store_true", help="write resolved values")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="explicit value (repeatable), wins over detection")
    ap.add_argument("--interactive", action="store_true", help="prompt for missing values")
    ap.add_argument("--force", action="store_true", help="overwrite existing settings values")
    ap.add_argument("--autonomous", action="store_true",
                    help="also register granular permissions.allow (plugin MCP + read-only bash + "
                         "pipeline write path) and permissions.deny (secret files)")
    ap.add_argument("--project", default=None, help="domain pack project_id (else auto-detect)")
    ap.add_argument("--json", action="store_true",
                    help="emit the check result as JSON on stdout instead of the text report; "
                         "for callers that drive the fix interaction themselves (see "
                         "/stablenet-expert:doctor). Never carries a secret's value.")
    args = ap.parse_args(argv)

    overrides: dict[str, str] = {}
    for item in args.set:
        if "=" not in item:
            print(f"error: --set expects KEY=VALUE, got {item!r}", file=sys.stderr)
            return 2
        k, v = item.split("=", 1)
        overrides[k.strip()] = v.strip()

    repo_root = _repo_root()
    claude_dir = repo_root / ".claude"
    detected = _detect(repo_root)
    persisted = _persisted(claude_dir)
    rre = _repo_root_env(_plugin_root(), repo_root, args.project)

    resolved: dict[str, tuple[str | None, str]] = {}
    for key, _where, _desc, _hint in REQUIRED:
        resolved[key] = _resolve(key, overrides, persisted, detected)

    # Interactive fallback for anything still unresolved.
    if args.interactive:
        for key, _where, desc, hint in REQUIRED:
            if resolved[key][0] is None:
                if hint:
                    print(f"  {key}: {hint}")
                try:
                    ans = input(f"{key} ({desc}): ").strip()
                except EOFError:
                    ans = ""
                if ans:
                    resolved[key] = (ans, "set")

    chainbench_mcp = shutil.which("chainbench-mcp")

    # --json: the machine-readable face of --check. A caller (doctor) needs three
    # things per key that the text report only half-carries: what the value is FOR
    # (desc), where to get it (hint), and whether this key can be written without
    # asking the user for anything (auto_fixable). Secrets never carry a value here
    # — the flag exists so a caller can present choices, not so it can read tokens.
    if args.json:
        rows = []
        for key, where, desc, hint in REQUIRED:
            val, src = resolved[key]
            rows.append({
                "key": key,
                "kind": where,
                "description": desc,
                "how_to_find": hint,
                "status": "missing" if val is None else src,
                "auto_fixable": val is not None and src != "project",
                "secret": where == SECRET,
            })
        print(json.dumps({
            "plugin": "core-dev",
            "project": str(repo_root),
            "rows": rows,
            "missing": [r["key"] for r in rows if r["status"] == "missing"],
            "auto_fixable": [r["key"] for r in rows if r["auto_fixable"]],
            "chainbench_mcp": chainbench_mcp or None,
            "repo_root_env": rre,
        }, indent=2))
        return 0 if not [r for r in rows if r["status"] == "missing"] else 1

    # Report.
    print(f"core-dev setup — project: {repo_root}")
    print(f"  {'KEY':<18} {'STATUS':<10} SOURCE / VALUE")
    missing = []
    for key, where, _desc, hint in REQUIRED:
        val, src = resolved[key]
        if val is None:
            missing.append(key)
            print(f"  {key:<18} {'MISSING':<10} -> needs --set {key}=... or --interactive")
            if hint:
                print(f"  {'':<18} {'':<10} where to get it: {hint}")
        else:
            shown = "********" if where == SECRET else val
            note = " (global; --fix would still write a project-local copy)" if src == "global" else ""
            print(f"  {key:<18} {src.upper():<10} {shown}  [{where}]{note}")
    print(f"  {'chainbench-mcp':<18} {'OK' if chainbench_mcp else 'NOT ON PATH':<10} "
          f"{chainbench_mcp or '-> install chainbench so chainbench-mcp is on PATH'}")
    is_plugin_repo = bool(repo_root) and (
        (repo_root / ".claude-plugin").is_dir()
        or (repo_root / "plugins" / "core-dev" / ".claude-plugin").is_dir())
    pin_rre = bool(rre) and not (is_plugin_repo and not args.project)
    if rre and pin_rre:
        print(f"  {rre:<18} {'REPO-ROOT':<10} {repo_root}  [{PUBLIC}] (active pack repo_root_env)")
    elif rre:
        print(f"  {rre:<18} {'MISMATCH':<10} cwd is the stablenet-expert plugin repo, not a target "
              "project — repo_root_env NOT written (run from the target repo, or pass --project)")
    else:
        print(f"  {'repo_root_env':<18} {'UNKNOWN':<10} "
              "could not resolve active pack — pass --project <id>")
    print(f"  {'permissions':<18} {'NOTE':<10} "
          "--autonomous registers granular allow (MCP + read-only bash + edits/build/"
          "feature-branch git) and deny (secret files); merge/tag stay prompted")

    # --autonomous: register the allow/deny lists independent of --fix / env resolution.
    if args.autonomous:
        w_allow = _merge_allow(claude_dir / "settings.local.json", AUTONOMOUS_ALLOW)
        w_deny = _merge_deny(claude_dir / "settings.local.json", AUTONOMOUS_DENY)
        _ensure_gitignored(repo_root, ".claude/settings.local.json")
        print(f"\nregistered {len(w_allow)} permission(s) to .claude/settings.local.json allow"
              + (f": {', '.join(w_allow)}" if w_allow else " (already present)"))
        print(f"registered {len(w_deny)} permission(s) to .claude/settings.local.json deny"
              + (f": {', '.join(w_deny)}" if w_deny else " (already present)"))

    if not args.fix:
        if missing:
            print(f"\n{len(missing)} value(s) unresolved: {', '.join(missing)}")
            print("run again with --fix (and --set KEY=VALUE for the missing ones, or --interactive)")
            return 1
        if not args.autonomous:
            print("\nall required values resolved. run with --fix to write them.")
        return 0

    # --fix: write resolved env into the two settings files (claude_dir defined above).
    public_vals = {k: resolved[k][0] for k, w, _, _ in REQUIRED if w == PUBLIC and resolved[k][0]}
    secret_vals = {k: resolved[k][0] for k, w, _, _ in REQUIRED if w == SECRET and resolved[k][0]}
    if pin_rre:
        public_vals[rre] = str(repo_root)   # pin active pack's repo_root_env to this repo

    w_pub = _merge_env(claude_dir / "settings.json", public_vals, args.force)
    w_sec = _merge_env(claude_dir / "settings.local.json", secret_vals, args.force)
    if w_sec:
        _ensure_gitignored(repo_root, ".claude/settings.local.json")

    print(f"\nwrote {len(w_pub)} key(s) to .claude/settings.json: {', '.join(w_pub) or '(none)'}")
    print(f"wrote {len(w_sec)} key(s) to .claude/settings.local.json: {', '.join(w_sec) or '(none)'}")
    if rre and not pin_rre:
        print(f"skipped {rre} (cwd is the plugin repo, not a target project)")
    if missing:
        print(f"still MISSING (provide via --set / --interactive): {', '.join(missing)}")
        return 1
    print("settings registered. restart the Claude Code session so the MCP servers pick up the env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
