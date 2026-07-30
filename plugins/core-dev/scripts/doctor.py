#!/usr/bin/env python3
"""doctor.py — read-only environment diagnostics for the core-dev plugin.

Deterministic checks only (no LLM, no MCP): active plugin version, project/repo,
active domain pack + project_id, env vars (process env + .claude/settings*.json,
secrets masked, restart-needed detection), stablenet-knowledge config source_root, and
permissions/allowlist. The `/core-dev:doctor` command runs this, then adds the
LIVE MCP health probes (stablenet-knowledge/chainbench/jira) and the final verdict.

    python3 doctor.py --plugin-root "$CLAUDE_PLUGIN_ROOT" [--project-id ID] [--json]

Run from the target project root (so `git rev-parse` resolves the repo). Stdlib
only; PyYAML is used opportunistically to read the stablenet-knowledge config's source_root.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

SECRETS = {"JIRA_API_TOKEN"}
ENV_KEYS = ["STABLENET_KNOWLEDGE_CONFIG", "STABLENET_KNOWLEDGE_MCP_BIN", "CHAINBENCH_DIR",
            "JIRA_BASE_URL", "JIRA_USER_EMAIL", "JIRA_API_TOKEN"]

# Single-source fix table (ADR doctor-remediation-2026-06-26). Maps every finding
# kind -> {action, command, klass}. klass classifies who resolves it:
#   setup    -> our setup.py writes it       (/core-dev:setup ...)
#   restart  -> session restart picks it up
#   manual   -> user decision / reconfigure  (rewire, cd, confirm)
#   external -> build/install outside the plugin (docs/SETUP.md)
# Keys cover both what doctor.py emits AND the live-MCP findings that
# commands/doctor.md routes (defined here so the mapping has one home).
REMEDIATION = {
    # --- emitted by doctor.py ---
    "no_plugin_root":      {"klass": "manual",  "command": "",
                            "action": "pass --plugin-root (the /core-dev:doctor command sets it automatically)"},
    "not_git":             {"klass": "manual",  "command": "",
                            "action": "cd to the target project root, then re-run /core-dev:doctor"},
    "project_id_unresolved": {"klass": "manual", "command": "--project <id>",
                            "action": "pass --project <id> to doctor and setup"},
    "repo_root_env_unset": {"klass": "setup",   "command": "/core-dev:setup --fix",
                            "action": "pin the active pack's repo_root_env, then restart the session"},
    "stablenet_knowledge_config_missing_file": {"klass": "external", "command": "see docs/SETUP.md",
                            "action": "fix STABLENET_KNOWLEDGE_CONFIG path or rebuild the stablenet-knowledge index"},
    "env_unset":           {"klass": "setup",   "command": "/core-dev:setup --fix",
                            "action": "detect & write the missing path env vars, then restart"},
    "env_secret_unset":    {"klass": "setup",   "command": "/core-dev:setup --fix --set <KEY>=<value>",
                            "action": "provide the secret explicitly, then restart"},
    "restart_needed":      {"klass": "restart", "command": "exit, then `claude --continue`",
                            "action": "restart the Claude Code session so MCP servers read the new env"},
    "permissions_unset":   {"klass": "setup",   "command": "/core-dev:setup --autonomous",
                            "action": "register a granular allowlist (only if you want unattended runs)"},
    # --- routed by commands/doctor.md from LIVE MCP probes (script cannot see these) ---
    "stablenet_knowledge_not_serviceable": {"klass": "manual",  "command": "",
                            "action": "start ckv/Ollama or rewire STABLENET_KNOWLEDGE_CONFIG, then restart the session"},
    "source_root_mismatch": {"klass": "manual", "command": "",
                            "action": "reconfigure the stablenet-knowledge config to index THIS repo, then restart"},
    "index_stale":         {"klass": "manual",  "command": "",
                            "action": "reindex — but skip if this is an intended base index (confirm first)"},
    "mcp_unreachable":     {"klass": "manual",  "command": "",
                            "action": "verify the MCP server is installed/enabled; restart Claude Code"},
    "stablenet_knowledge_mcp_not_built":   {"klass": "external", "command": "see docs/SETUP.md",
                            "action": "build stablenet-knowledge-mcp (make) so STABLENET_KNOWLEDGE_MCP_BIN resolves"},
    "chainbench_not_installed": {"klass": "external", "command": "see docs/SETUP.md",
                            "action": "install chainbench so chainbench-mcp is on PATH"},
}
KLASSES = {"setup", "restart", "manual", "external"}


def _add_issue(out: dict, kind: str, detail: str) -> None:
    """Append a structured issue. `kind` MUST exist in REMEDIATION (gate-checked)."""
    out["issues"].append({"kind": kind, "detail": detail})


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    except Exception:
        return ""


def _load_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _mask(key: str, val):
    return "********" if (key in SECRETS and val) else val


def detect_project_id(plugin_root: Path, repo_root: str, override):
    """Resolve project_id: --project-id > single pack > repo-name/remote match > None."""
    domains = plugin_root / "domains"
    packs = sorted(d.name for d in domains.glob("*")
                   if (d / "domain-pack.json").is_file()) if domains.is_dir() else []
    if override:
        return override, packs
    if len(packs) == 1:
        return packs[0], packs
    base = Path(repo_root).name if repo_root else ""
    remote = _run(["git", "-C", repo_root or ".", "remote", "get-url", "origin"])
    for pid in packs:
        if pid and (pid in base or pid in remote):
            return pid, packs
    return None, packs


def diagnose(plugin_root: Path | None, project_id_override) -> dict:
    out: dict = {"issues": [], "restart_needed": []}

    # --- plugin ---
    ver = "?"
    if plugin_root:
        ver = _load_json(plugin_root / ".claude-plugin" / "plugin.json").get("version", "?")
    out["plugin"] = {"active_version": ver, "plugin_root": str(plugin_root) if plugin_root else None}
    if not plugin_root:
        _add_issue(out, "no_plugin_root",
                   "CLAUDE_PLUGIN_ROOT not provided; cannot read active version/packs")

    # --- project / repo ---
    repo_root = _run(["git", "rev-parse", "--show-toplevel"])
    head = _run(["git", "rev-parse", "--short", "HEAD"])
    out["project"] = {"cwd": os.getcwd(), "is_git": bool(repo_root),
                      "repo_root": repo_root or None, "head": head or None}
    if not repo_root:
        _add_issue(out, "not_git", "not inside a git repo")

    # --- domain pack / project_id ---
    pid, packs, repo_root_env = None, [], None
    if plugin_root:
        pid, packs = detect_project_id(plugin_root, repo_root, project_id_override)
        if pid:
            pack = _load_json(plugin_root / "domains" / pid / "domain-pack.json")
            repo_root_env = (pack.get("verification") or {}).get("repo_root_env")
        else:
            _add_issue(out, "project_id_unresolved", f"could not resolve project_id (packs={packs})")
    out["domain_pack"] = {"project_id": pid, "available_packs": packs, "repo_root_env": repo_root_env}

    # --- env vars (process + settings) ---
    settings = _load_json(Path(repo_root) / ".claude" / "settings.json") if repo_root else {}
    slocal = _load_json(Path(repo_root) / ".claude" / "settings.local.json") if repo_root else {}
    senv = {**settings.get("env", {}), **slocal.get("env", {})}
    keys = ([repo_root_env] if repo_root_env else []) + ENV_KEYS
    env_report = {}
    seen = set()
    for k in keys:
        if not k or k in seen:
            continue
        seen.add(k)
        pv, sv = os.environ.get(k), senv.get(k)
        status = "ok" if pv else ("restart_needed" if sv else "unset")
        env_report[k] = {"process": _mask(k, pv), "settings": _mask(k, sv), "status": status}
        if sv and not pv:
            out["restart_needed"].append(k)
        elif not pv and not sv and k == repo_root_env:
            _add_issue(out, "repo_root_env_unset",
                       f"{k} unset — repo_root falls back to git rev-parse; setup --fix can pin it")
    out["env"] = env_report

    # --- stablenet-knowledge config (presence only) ---
    # source_root / indexed_head coherence is probed LIVE by the command via
    # cks_ops_health (authoritative); the yaml schema nests it under backends and
    # varies, so we do not parse it here.
    cks_cfg = os.environ.get("STABLENET_KNOWLEDGE_CONFIG") or senv.get("STABLENET_KNOWLEDGE_CONFIG")
    cks = {"path": cks_cfg, "exists": bool(cks_cfg and Path(cks_cfg).is_file()),
           "note": "source_root / freshness checked live by the command (cks_ops_health)"}
    if cks_cfg and not Path(cks_cfg).is_file():
        _add_issue(out, "stablenet_knowledge_config_missing_file", f"STABLENET_KNOWLEDGE_CONFIG points to a missing file: {cks_cfg}")
    out["stablenet_knowledge_config"] = cks

    # --- permissions / allowlist ---
    perms = settings.get("permissions", {})
    allow = perms.get("allow", []) or []
    allowlisted = any("core-dev" in str(x) for x in allow)
    out["permissions"] = {"defaultMode": perms.get("defaultMode"),
                          "plugin_allowlisted": allowlisted,
                          "allow_count": len(allow)}

    out["verdict"] = "READY" if not out["issues"] and not out["restart_needed"] else "ATTENTION"
    out["remediations"] = _remediations(out, repo_root_env, allowlisted)
    return out


def _remediations(out: dict, repo_root_env, allowlisted: bool) -> list[dict]:
    """Ordered, de-duplicated next-actions. Supersets issues with advisories
    (unset env, missing allowlist) that guide toward setup without flipping verdict."""
    rem: list[dict] = []
    seen: set[str] = set()

    def add(kind: str, detail: str = "") -> None:
        if kind in seen:
            return
        seen.add(kind)
        r = REMEDIATION.get(kind, {})
        rem.append({"kind": kind, "klass": r.get("klass", "manual"),
                    "command": r.get("command", ""), "action": r.get("action", ""),
                    "detail": detail})

    for it in out["issues"]:
        add(it["kind"], it.get("detail", ""))
    if out["restart_needed"]:
        add("restart_needed", ", ".join(out["restart_needed"]))
    # advisory: required path env vars unset (neither process nor settings); setup --fix can write them.
    # repo_root_env has its own issue, so exclude it here to avoid a duplicate line.
    unset = [k for k, e in out["env"].items()
             if e["status"] == "unset" and k not in SECRETS and k != repo_root_env]
    if unset:
        add("env_unset", ", ".join(unset))
    unset_secret = [k for k, e in out["env"].items()
                    if e["status"] == "unset" and k in SECRETS]
    if unset_secret:
        add("env_secret_unset", ", ".join(unset_secret))
    if not allowlisted:
        add("permissions_unset", "plugin tools not in permissions.allow")
    return rem


def render(out: dict) -> str:
    L = [f"core-dev doctor — {out['verdict']}  (deterministic; MCP probes added by the command)"]
    p = out["plugin"]; L.append(f"  plugin     : v{p['active_version']}  ({p['plugin_root']})")
    pr = out["project"]; L.append(f"  project    : {pr['repo_root'] or pr['cwd']} @ {pr['head'] or '-'} (git={pr['is_git']})")
    dp = out["domain_pack"]
    L.append(f"  domain pack: project_id={dp['project_id']} packs={dp['available_packs']} repo_root_env={dp['repo_root_env']}")
    L.append("  env:")
    for k, e in out["env"].items():
        L.append(f"    {k:<18} {e['status']:<14} process={e['process'] or '-'}  settings={e['settings'] or '-'}")
    c = out["stablenet_knowledge_config"]
    L.append(f"  stablenet_knowledge_config : {c['path'] or '-'}  exists={c['exists']}  (source_root/freshness: live probe)")
    pm = out["permissions"]
    L.append(f"  permissions: defaultMode={pm['defaultMode']} plugin_allowlisted={pm['plugin_allowlisted']} (allow={pm['allow_count']})")
    if out["restart_needed"]:
        L.append(f"  ⚠ restart needed (in settings, not in current env): {', '.join(out['restart_needed'])}")
    if out["issues"]:
        L.append("  issues:")
        L += [f"    - [{i['kind']}] {i['detail']}" for i in out["issues"]]
    rem = out.get("remediations", [])
    if rem:
        L.append("  remediation (next actions):")
        for r in rem:
            tgt = r["command"] or r["action"]
            extra = f"  ({r['action']})" if r["command"] and r["action"] else ""
            L.append(f"    → [{r['klass']}] {tgt}{extra}"
                     + (f"  — {r['detail']}" if r["detail"] else ""))
    # one-line summary
    if out["verdict"] == "READY":
        tail = f"READY — {len(rem)} optional action(s)" if rem else "READY"
    else:
        cmds = [r["command"] for r in rem if r["command"]]
        uniq = list(dict.fromkeys(cmds))
        tail = f"ATTENTION — {len(rem)} action(s)" + (f": {'; '.join(uniq)}" if uniq else "")
    L.append(f"  => {tail}")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="core-dev environment diagnostics (read-only)")
    ap.add_argument("--plugin-root", default=os.environ.get("CLAUDE_PLUGIN_ROOT", ""))
    ap.add_argument("--project-id", "--project", dest="project_id", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    out = diagnose(Path(a.plugin_root) if a.plugin_root else None, a.project_id)
    print(json.dumps(out, indent=2) if a.json else render(out))
    return 0 if out["verdict"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
