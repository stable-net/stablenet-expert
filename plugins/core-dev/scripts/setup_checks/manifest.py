#!/usr/bin/env python3
"""Provenance manifest — what setup wrote, so uninstall can take back only that.

`claude plugin uninstall` removes the plugin and nothing else: env keys, permission
entries and gitignore lines that setup wrote all survive it. Cleaning them up needs an
answer to "which of these are ours", and the settings files do not carry one -- a key we
wrote and a key the user set by hand look identical.

So `--fix` records what it wrote, and `--uninstall` removes only entries whose *current
value still matches what we recorded*. A value that has since changed is left alone and
reported: the user edited it after we wrote it, and silently reverting an edit is worse
than leaving a stale key behind. This is the rule package managers apply to config files
they ship (dpkg's conffiles), for the same reason.

The manifest sits beside the settings it describes rather than in them, so a settings file
stays a settings file -- nothing downstream has to learn to ignore a bookkeeping key. If it
is lost, uninstall removes nothing and says so, which is the safe direction.

Stdlib only, per ADR-0014.
"""

from __future__ import annotations

import json
from pathlib import Path

FILENAME = ".stablenet-expert-managed.json"
VERSION = 1


def path_for(claude_dir: Path) -> Path:
    return claude_dir / FILENAME


def load(claude_dir: Path) -> dict:
    p = path_for(claude_dir)
    try:
        doc = json.loads(p.read_text())
    except (OSError, ValueError):
        return {"version": VERSION, "env": {}, "permissions": {"allow": [], "deny": []},
                "gitignore": []}
    doc.setdefault("env", {})
    doc.setdefault("permissions", {}).setdefault("allow", [])
    doc["permissions"].setdefault("deny", [])
    doc.setdefault("gitignore", [])
    return doc


def _save(claude_dir: Path, doc: dict) -> None:
    doc["version"] = VERSION
    p = path_for(claude_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def record_env(claude_dir: Path, file_name: str, values: dict[str, str]) -> None:
    """Note that `values` were written into <claude_dir>/<file_name>'s env block.

    The value is stored alongside the key. Recording only the name would let uninstall
    delete a value the user replaced afterwards -- the manifest would say "ours" about a
    key holding someone else's content.
    """
    if not values:
        return
    doc = load(claude_dir)
    for key, value in values.items():
        doc["env"][key] = {"value": value, "file": file_name}
    _save(claude_dir, doc)


def record_permissions(claude_dir: Path, allow: list[str], deny: list[str]) -> None:
    if not allow and not deny:
        return
    doc = load(claude_dir)
    for entry in allow:
        if entry not in doc["permissions"]["allow"]:
            doc["permissions"]["allow"].append(entry)
    for entry in deny:
        if entry not in doc["permissions"]["deny"]:
            doc["permissions"]["deny"].append(entry)
    _save(claude_dir, doc)


def record_gitignore(claude_dir: Path, line: str) -> None:
    doc = load(claude_dir)
    if line not in doc["gitignore"]:
        doc["gitignore"].append(line)
        _save(claude_dir, doc)


def plan_removal(claude_dir: Path, read_settings) -> dict:
    """What --uninstall would take back, without taking anything back.

    `read_settings(file_name)` returns that settings file as a dict. Returns three lists:

      remove   -- recorded, and the value on disk is still the one we wrote
      changed  -- recorded, but the value differs now; left alone, reported
      absent   -- recorded, already gone; nothing to do

    Splitting `changed` out is the whole point of storing values. Without it uninstall is a
    blind delete of every key the table names.
    """
    doc = load(claude_dir)
    cache: dict[str, dict] = {}
    remove, changed, absent = [], [], []

    for key, rec in sorted(doc["env"].items()):
        file_name = rec.get("file", "settings.json")
        if file_name not in cache:
            cache[file_name] = (read_settings(file_name) or {}).get("env") or {}
        current = cache[file_name].get(key)
        if current is None:
            absent.append({"key": key, "file": file_name})
        elif current == rec.get("value"):
            remove.append({"key": key, "file": file_name})
        else:
            changed.append({"key": key, "file": file_name})

    return {
        "env": {"remove": remove, "changed": changed, "absent": absent},
        "permissions": dict(doc["permissions"]),
        "gitignore": list(doc["gitignore"]),
        "manifest": str(path_for(claude_dir)),
        "manifest_exists": path_for(claude_dir).is_file(),
    }
