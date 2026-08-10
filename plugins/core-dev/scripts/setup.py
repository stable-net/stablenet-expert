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

Where values go: env values land in the *user* settings (~/.claude/settings.json) so they
apply to every project -- they describe this machine, not this checkout. The active pack's
repo_root_env is the exception and stays project-local. --scope project forces both local.

Uninstall: --fix records what it wrote (key *and* value) in a manifest beside the settings,
so --uninstall can take back exactly that and nothing else. A value changed since we wrote
it is kept and reported.

Modes:
  --check        report status, exit 1 if any REQUIRED value is unresolved (default)
  --fix          write resolved values into the settings files (idempotent merge)
  --set K=V      provide a value explicitly (repeatable); wins over detection
  --interactive  prompt on stdin for any value still missing (human terminal use)
  --force        overwrite values already present in settings (default: keep them)
  --scope        user (default) | project -- where env values are written
  --uninstall    remove what --fix wrote (dry run; --yes to apply)
  --with-plugins with --fix, also install/authenticate external plugin dependencies
                 (opt-in: installs into the user's Claude Code and opens a browser)

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

# Dependency modules. setup.py owns the contract surface; each module owns one
# dependency's state logic. Importable because running a script puts its directory
# on sys.path[0].
from setup_checks import atlassian, manifest, validate

# (key, where, description, how-to-find)
# Sources that survive the session. _resolve reports one of
# {set, project, global, env, detected, none}; only these two are written down.
PERSISTED_SOURCES = ("project", "global")

# An address is not a credential. Withholding endpoints made doctor ask the user to approve a
# value it would not show them, which is not consent -- and a setup tool that cannot show or
# accept connection details cannot do its job. Credentials are still withheld: that is what the
# SECRET column and setup_checks/validate.py are for.

# Which MCP server each value serves. The caller groups its questions by this, and it has to
# come from here: doctor owns no knowledge of another plugin's environment (ADR-0011 §2.2), so
# inferring the grouping from key names there would be exactly the guess that principle forbids.
# A key with no entry belongs to no server and is not grouped -- repo_root_env, for one.
SERVES = {
    "STABLENET_KNOWLEDGE_MCP_URL": "stablenet-knowledge",
    "CHAINBENCH_DIR": "chainbench",
}

PUBLIC = "settings.json"
SECRET = "settings.local.json"

REQUIRED = [
    ("STABLENET_KNOWLEDGE_MCP_URL", PUBLIC,
     "stablenet-knowledge server endpoint -- the retrieval the planner runs on. Without it the "
     "MCP server cannot start, and the pipeline plans against whatever the model already knows "
     "instead of against this codebase",
     "the http://host:port/mcp address of the server your team runs; ask whoever operates it"),
    ("CHAINBENCH_DIR", PUBLIC, "chainbench checkout directory",
     "sibling chainbench repo's checkout path"),
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
    "mcp__plugin_atlassian_atlassian__*",
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
    # Read-only git the pipeline reaches through `git -C <repo> ...`, which hides the subcommand
    # from a "git <verb>:*" pattern until you go looking. merge syncs the local branch with
    # `git pull --ff-only`; the analyzer reads history through merge-base and symbolic-ref;
    # implementer parks work with stash. Every one of these was prompting.
    "Bash(git pull:*)", "Bash(git fetch:*)", "Bash(git merge-base:*)",
    "Bash(git symbolic-ref:*)", "Bash(git stash:*)",
    # gh beyond `gh pr`: the review flow pages PR comments through the REST API, and two
    # commands check that gh is authenticated before doing anything. Scoped to repos/ so it
    # cannot reach the rest of the API surface.
    "Bash(gh api repos/:*)", "Bash(gh auth status:*)",
    # Read-only process check the Evaluator uses to see whether a chain is already up.
    "Bash(pgrep:*)",
    # PR creation/inspection only — merge stays with /core-dev:merge
    "Bash(gh pr create:*)", "Bash(gh pr view:*)", "Bash(gh pr list:*)",
    "Bash(gh pr checks:*)",
]

# --autonomous also registers permissions.deny: secret files the agent must never
# read via the Read tool, even while the allowlist above is active (defense-in-depth;
# mirrors gsd-core's installer denies).
AUTONOMOUS_DENY = [
    "Read(.env)",
    "Read(.env.*)",
    "Read(.secrets)",
    "Read(.claude/settings.local.json)",
]



def _row_ready(row: dict) -> bool:
    """Is this dependency usable as-is?

    For an env value that means "resolved" -- a value detected but not yet written to
    settings still counts, matching the pre-existing exit-code contract (only `missing`
    made --check fail). For anything else, readiness is the module's own verdict, carried
    as `auto_fixable`: there is nothing left to fix exactly when nothing is wrong.
    """
    if row["row_kind"] == "env":
        # Only a persisted value counts. `env` means the value exists in *this process* and
        # nowhere on disk, so it disappears with the session -- Claude Code reads ${VAR} from
        # settings, not from whatever shell happened to start it. `detected` is a guess we have
        # not written down yet. Calling either "ready" is how a machine passes setup and then
        # fails to start its MCP servers the next morning.
        return row["status"] in PERSISTED_SOURCES
    return not row["auto_fixable"]


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
    base = repo_root.parent  # e.g. .../github/, sibling to chainbench
    found: dict[str, str] = {}

    # Nothing to detect for stablenet-knowledge: it is a remote HTTP server, so the only value
    # it needs is STABLENET_KNOWLEDGE_MCP_URL, which no amount of looking at this filesystem can
    # discover. It comes from whoever runs the server.
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



def _strip_env(path: Path, keys: list[str]) -> list[str]:
    """Delete `keys` from a settings file's env block. Returns what was actually removed."""
    doc = _load_json(path)
    env = doc.get("env")
    if not isinstance(env, dict):
        return []
    gone = [k for k in keys if env.pop(k, None) is not None]
    if gone:
        doc["env"] = env
        path.write_text(json.dumps(doc, indent=2) + "\n")
    return gone


def _strip_permissions(path: Path, allow: list[str], deny: list[str]) -> tuple[list[str], list[str]]:
    doc = _load_json(path)
    perms = doc.get("permissions")
    if not isinstance(perms, dict):
        return [], []
    out = []
    for name, wanted in (("allow", allow), ("deny", deny)):
        current = perms.get(name)
        if not isinstance(current, list):
            out.append([]); continue
        removed = [e for e in wanted if e in current]
        perms[name] = [e for e in current if e not in wanted]
        out.append(removed)
    if out[0] or out[1]:
        doc["permissions"] = perms
        path.write_text(json.dumps(doc, indent=2) + "\n")
    return out[0], out[1]


def _uninstall(claude_dir: Path, env_dir: Path, repo_root: Path, args) -> int:
    """Take back what --fix wrote, and only that.

    Dry run by default. Removing settings on someone's machine is not the kind of thing to do
    on the strength of a flag that could have been a typo, and the plan is the whole value of
    the manifest -- seeing "3 to remove, 1 changed by you" before anything happens is what
    makes this safe to run.
    """
    # Say which directories are being examined before saying what is in them. The project one
    # is derived from the current directory unless --repo names it, so running this from the
    # wrong place would otherwise clean the user scope, find nothing else, and look like it
    # succeeded.
    print(f"looking in:\n  {env_dir}" + (f"\n  {claude_dir}" if claude_dir != env_dir else ""))
    if claude_dir == env_dir:
        print("  (no project directory: the current directory is not inside a git repository,\n"
              "   so only user-scope settings are in scope. Pass --repo <path> to include a\n"
              "   project's own .claude/.)")
    elif not (repo_root / ".git").exists():
        print(f"  (note: {repo_root} has no .git — it was taken as the project because it is\n"
              "   the current directory. Pass --repo <path> if that is not what you meant.)")
    print()

    plans = []
    for d in ({env_dir, claude_dir} if env_dir != claude_dir else {claude_dir}):
        plan = manifest.plan_removal(d, lambda name, base=d: _load_json(base / name))
        plan["dir"] = d
        plans.append(plan)
    plans.sort(key=lambda p: str(p["dir"]))

    if not any(p["manifest_exists"] for p in plans):
        print("no manifest found — nothing recorded, so nothing is removed.")
        print("  A manifest is written by --fix. Without one there is no way to tell which")
        print("  settings this plugin wrote and which you set yourself, and guessing would")
        print("  mean deleting your values. Remove what you recognise by hand.")
        return 0

    total_remove = total_changed = 0
    for plan in plans:
        if not plan["manifest_exists"]:
            continue
        d = plan["dir"]
        print(f"\n{d}:")
        env = plan["env"]
        for row in env["remove"]:
            print(f"  remove  {row['key']:<24} ({row['file']})")
        for row in env["changed"]:
            print(f"  KEEP    {row['key']:<24} ({row['file']}) — value changed since we wrote it")
        for row in env["absent"]:
            print(f"  (gone)  {row['key']:<24} ({row['file']})")
        perms = plan["permissions"]
        if perms["allow"] or perms["deny"]:
            print(f"  remove  {len(perms['allow'])} allow / {len(perms['deny'])} deny entr(ies)")
        total_remove += len(env["remove"]) + len(perms["allow"]) + len(perms["deny"])
        total_changed += len(env["changed"])

    if not args.yes:
        print(f"\ndry run — nothing changed. {total_remove} item(s) would be removed"
              + (f", {total_changed} kept because you changed them" if total_changed else "")
              + ".\nre-run with --uninstall --yes to apply.")
        return 0

    for plan in plans:
        if not plan["manifest_exists"]:
            continue
        d = plan["dir"]
        by_file: dict[str, list[str]] = {}
        for row in plan["env"]["remove"]:
            by_file.setdefault(row["file"], []).append(row["key"])
        for file_name, keys in by_file.items():
            gone = _strip_env(d / file_name, keys)
            print(f"removed {len(gone)} key(s) from {d / file_name}: {', '.join(gone) or '(none)'}")
        perms = plan["permissions"]
        if perms["allow"] or perms["deny"]:
            a, dn = _strip_permissions(d / "settings.local.json", perms["allow"], perms["deny"])
            print(f"removed {len(a)} allow / {len(dn)} deny entr(ies) from "
                  f"{d / 'settings.local.json'}")
        manifest.path_for(d).unlink(missing_ok=True)

    print("\nsettings taken back. Two things are deliberately left to you:")
    print(f"  - the Atlassian MCP plugin, if setup installed it. It is shared -- you may use it")
    print(f"    for your own Jira work, and another plugin may need it. To drop it anyway:")
    print(f"      claude mcp logout {atlassian.SERVER}")
    print(f"      claude plugin uninstall {atlassian.PLUGIN}")
    print("  - the .gitignore line for .claude/settings.local.json, which is harmless and may")
    print("    predate this plugin.")
    print("\nThen: claude plugin uninstall core-dev@stablenet-expert")
    return 0


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
    ap.add_argument("--scope", choices=("user", "project"), default="user",
                    help="where env values are written: user (default, ~/.claude/settings.json, "
                         "applies everywhere) or project (this repo's .claude/). The active "
                         "pack's repo_root_env is always project-local either way.")
    ap.add_argument("--force-value", action="store_true",
                    help="write a --set value that failed validation. For the case where a "
                         "legitimate value trips the credential check; not for silencing a "
                         "shape error, which means the value is wrong.")
    ap.add_argument("--repo", default=None, metavar="PATH",
                    help="the project to act on. Defaults to the git root of the current "
                         "directory, which is why the plain command has to be run from inside "
                         "the project; pass this to run it from anywhere.")
    ap.add_argument("--uninstall", action="store_true",
                    help="remove what --fix wrote, using the provenance manifest. Values that "
                         "changed since we wrote them are left alone and reported. Add --yes to "
                         "skip the dry run.")
    ap.add_argument("--yes", action="store_true",
                    help="with --uninstall, actually remove (default is a dry run)")
    ap.add_argument("--with-plugins", action="store_true",
                    help="with --fix, also install and authenticate external plugin "
                         "dependencies (the Atlassian MCP). Opt-in because it reaches "
                         "outside this project -- it installs into the user's Claude Code "
                         "and opens a browser for an OAuth consent. --check always reports "
                         "on them; only acting needs this flag.")
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
        k, v = k.strip(), v.strip()
        reason = None if args.force_value else validate.check(k, v)
        if reason:
            # The value is never echoed back -- if it was refused for looking like a
            # credential, repeating it here would put it in the transcript a second time.
            print(f"error: {k} {reason}", file=sys.stderr)
            return 2
        overrides[k] = v

    repo_root = Path(args.repo).expanduser().resolve() if args.repo else _repo_root()
    if args.repo and not repo_root.is_dir():
        print(f"error: --repo {args.repo} is not a directory", file=sys.stderr)
        return 2
    # Where settings go. Two different questions live here, so they get two different answers
    # rather than one --scope flag covering both:
    #
    #   env values (CHAINBENCH_DIR, ...) describe *this machine* -- one chainbench checkout,
    #     one knowledge server -- so they belong in the user-global settings and apply to every
    #     project. That also matches scripts/set-mcp-env.sh, which has defaulted to user scope
    #     all along; setup.py writing project-only was the odd one out.
    #   repo_root_env answers "which checkout is the target", which is per project by
    #     definition, so it stays local. A project file overrides the global one, so someone
    #     with two checkouts can still pin each.
    #
    # --scope project forces both into the project, for a machine shared by several people or
    # a checkout that must not touch the global file.
    claude_dir = repo_root / ".claude"
    env_dir = claude_dir if args.scope == "project" else Path.home() / ".claude"
    detected = _detect(repo_root)
    persisted = _persisted(claude_dir)
    rre = _repo_root_env(_plugin_root(), repo_root, args.project)

    if args.uninstall:
        return _uninstall(claude_dir, env_dir, repo_root, args)

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
                # row_kind tells the caller what sort of thing this is, because the three
                # sorts need different handling: an env value can be written unattended, an
                # external plugin needs an install plus a browser consent. Without it a
                # caller would have to infer the difference from the key name.
                "row_kind": "env",
                "kind": where,
                "description": desc,
                "how_to_find": hint,
                "status": "missing" if val is None else src,
                # What would actually be written. The caller shows this before asking, because
                # "shall I set CHAINBENCH_DIR?" is not a question anyone can answer -- detection
                # can land on the wrong checkout, and approving a value you cannot see is not
                # consent. Secrets stay out: a row that carries one is not printable.
                "serves": SERVES.get(key),
                "resolved_value": None if (val is None or where == SECRET) else val,
                # Why the value is absent, so the caller can say "set, not shown" rather than
                # implying nothing is configured.
                "value_withheld": bool(val is not None and where == SECRET),
                "auto_fixable": val is not None and src != "project",
                "opens_browser": False,
                "secret": where == SECRET,
            })
        rows.append(atlassian.row(atlassian.check()))
        print(json.dumps({
            "plugin": "core-dev",
            "project": str(repo_root),
            "rows": rows,
            "missing": [r["key"] for r in rows if r["status"] == "missing"],
            "auto_fixable": [r["key"] for r in rows if r["auto_fixable"]],
            # Anything not yet usable, whatever its row_kind. "missing" alone does not
            # cover it: an installed-but-unauthenticated plugin is present and still
            # unusable, so a caller checking only `missing` would call the setup done.
            "not_ready": [r["key"] for r in rows if not _row_ready(r)],
            "chainbench_mcp": chainbench_mcp or None,
            "repo_root_env": rre,
        }, indent=2))
        return 0 if all(_row_ready(r) for r in rows) else 1

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
    # repo_root is a *guess*: _repo_root() falls back to the working directory when git says
    # nothing, so running from a folder that merely contains checkouts pins that folder. The
    # Evaluator then runs the pack's build and test commands there and fails on a directory
    # that was never a project. Refuse the two guesses that are visibly wrong rather than
    # writing them and letting the failure surface three stages later.
    not_a_repo = bool(repo_root) and not (repo_root / ".git").exists()
    pin_rre = bool(rre) and not (is_plugin_repo and not args.project) and not not_a_repo
    if rre and pin_rre:
        print(f"  {rre:<18} {'REPO-ROOT':<10} {repo_root}  [{PUBLIC}] (active pack repo_root_env)")
    elif rre and not_a_repo:
        print(f"  {rre:<18} {'NOT-A-REPO':<10} {repo_root} has no .git — repo_root_env NOT written.")
        print(f"  {'':<18} {'':<10} This value names the checkout the pipeline builds and tests, so")
        print(f"  {'':<18} {'':<10} run setup from inside it (or pass --repo <path>).")
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
        manifest.record_permissions(claude_dir, w_allow, w_deny)
        manifest.record_gitignore(claude_dir, ".claude/settings.local.json")
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

    # repo_root_env is per project by definition, so it stays in the project file whatever
    # --scope says; the rest follows the scope.
    pinned = {rre: public_vals.pop(rre)} if pin_rre and rre in public_vals else {}

    w_pub = _merge_env(env_dir / "settings.json", public_vals, args.force)
    w_sec = _merge_env(env_dir / "settings.local.json", secret_vals, args.force)
    w_pin = _merge_env(claude_dir / "settings.json", pinned, args.force) if pinned else []
    if w_sec and env_dir == claude_dir:
        _ensure_gitignored(repo_root, ".claude/settings.local.json")
        manifest.record_gitignore(claude_dir, ".claude/settings.local.json")

    # Record what was written, keyed to the directory it went into, so --uninstall run from
    # either scope takes back exactly what that scope holds.
    manifest.record_env(env_dir, "settings.json", {k: public_vals[k] for k in w_pub})
    manifest.record_env(env_dir, "settings.local.json", {k: secret_vals[k] for k in w_sec})
    if w_pin:
        manifest.record_env(claude_dir, "settings.json", {k: pinned[k] for k in w_pin})

    where = "~/.claude" if env_dir != claude_dir else ".claude"
    print(f"\nwrote {len(w_pub)} key(s) to {where}/settings.json: {', '.join(w_pub) or '(none)'}")
    print(f"wrote {len(w_sec)} key(s) to {where}/settings.local.json: {', '.join(w_sec) or '(none)'}")
    if pinned:
        print(f"wrote {len(w_pin)} key(s) to .claude/settings.json (project-local): "
              f"{', '.join(w_pin) or '(none)'}")

    # External plugin dependency. Last, because it is the only step that can block on a
    # human: it opens a browser for the OAuth grant. Doing the settings writes first means
    # a user who abandons the consent still keeps everything else this run resolved.
    if args.with_plugins:
        before = atlassian.check()
        if before["status"] == atlassian.READY:
            print(f"atlassian MCP: {before['detail']}")
        else:
            print(f"atlassian MCP: {before['detail']} -- installing/authenticating "
                  f"(a browser window will open; {atlassian.LOGIN_TIMEOUT_SECONDS}s to consent)")
            result = atlassian.fix()
            print(f"atlassian MCP: {result['detail']}")
            if result["status"] != atlassian.READY:
                # Not fatal to the rest of setup, but never silent: a caller that reports
                # "done" here would send the user off to restart into a broken pipeline.
                print(f"atlassian MCP: NOT READY ({result['status']}) -- "
                      f"finish it yourself with: claude mcp login {atlassian.SERVER}")
    else:
        # Not asked to act on it, but say where it stands: a --fix that printed only its
        # settings writes would read as "setup complete" while the pipeline's ticket source
        # is still unusable.
        state = atlassian.check()
        if state["status"] != atlassian.READY:
            print(f"atlassian MCP: {state['detail']} -- not touched "
                  f"(re-run with --with-plugins, or: claude mcp login {atlassian.SERVER})")
    if rre and not pin_rre:
        print(f"skipped {rre} (cwd is the plugin repo, not a target project)")
    if missing:
        print(f"still MISSING (provide via --set / --interactive): {', '.join(missing)}")
        return 1
    print("settings registered. restart the Claude Code session so the MCP servers pick up the env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
