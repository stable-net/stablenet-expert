#!/usr/bin/env python3
"""Which model families actually ran in this session — main thread vs sub-agents.

Why this exists: a sub-agent's `model:` frontmatter is a request. When it does not
resolve, Claude Code falls back to the parent model and logs at `warn` — invisible in
normal use. For most agents that costs quality or money. For `review-adjudicator` it
costs the guarantee: its entire purpose is to be a *different* model from the one that
wrote the findings, because the failure it guards against is a confident misreading,
and a model rarely catches its own. Collapsed onto one model it still returns verdicts,
and the review still reports itself as adjudicated.

So the claim gets checked instead of assumed. The session transcript records
`message.model` per message and marks sub-agent turns with `isSidechain`, which is
enough to say whether two different families ran.

**Model ids never leave this script.** On Bedrock an id is a region-prefixed inference
profile or an ARN — an internal cloud resource identifier under the group security
policy — so output is the *family* only (`opus`, `sonnet`, ...), extracted by matching
a known family name. An id no family matches is reported as `unidentifiable`, never
echoed. That is also why an unreadable transcript is not treated as "probably fine":
see `--require-distinct`.

    python3 session_models.py                      # report families, exit 0
    python3 session_models.py --require-distinct   # exit 1 unless a sub-agent family
                                                   # differs from the main thread
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Families Claude Code names its models after. Order matters only for readability.
FAMILIES = ("opus", "sonnet", "haiku", "fable", "mythos")
UNIDENTIFIABLE = "unidentifiable"
SYNTHETIC = "<synthetic>"

_PROJECTS = Path.home() / ".claude" / "projects"


def family_of(model_id: str) -> str:
    """Reduce a provider-specific id to its family name, or `unidentifiable`.

    Never returns any part of the input: a caller that prints this cannot leak a
    region prefix, an account id or an ARN.
    """
    low = model_id.lower()
    for fam in FAMILIES:
        if re.search(rf"(^|[^a-z]){fam}([^a-z]|$)", low):
            return fam
    return UNIDENTIFIABLE


def find_transcript(session_id: str | None = None,
                    projects_dir: Path | None = None,
                    cwd: str | None = None) -> Path | None:
    """Locate this session's JSONL. Prefers CLAUDE_SESSION_ID over a newest-file guess."""
    root = projects_dir or _PROJECTS
    if not root.is_dir():
        return None
    sid = session_id or os.environ.get("CLAUDE_SESSION_ID") or ""
    if sid:
        hits = sorted(root.glob(f"*/{sid}.jsonl"))
        if hits:
            return hits[0]
    # Fall back to the newest transcript for this working directory. Claude Code slugs
    # the cwd into the directory name, so match on that rather than across every project.
    slug = re.sub(r"[^A-Za-z0-9]+", "-", cwd or os.getcwd())
    candidates = list((root / slug).glob("*.jsonl")) if (root / slug).is_dir() else []
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def scan(path: Path) -> dict:
    """Families seen on the main thread and in sub-agent (sidechain) turns."""
    main: dict[str, int] = {}
    sub: dict[str, int] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue          # tolerate a partial trailing write
            msg = rec.get("message")
            if not isinstance(msg, dict):
                continue
            model = msg.get("model")
            if not model or model == SYNTHETIC:
                continue
            bucket = sub if rec.get("isSidechain") else main
            fam = family_of(model)
            bucket[fam] = bucket.get(fam, 0) + 1
    return {"main": main, "subagent": sub}


def verdict(families: dict) -> dict:
    """Did any sub-agent run on a family the main thread did not?"""
    main = set(families["main"])
    sub = set(families["subagent"])
    distinct = sorted(sub - main)
    # No sub-agent turns at all is not evidence of independence -- it is no evidence.
    return {
        "main_families": sorted(main),
        "subagent_families": sorted(sub),
        "distinct_subagent_families": distinct,
        "has_distinct": bool(distinct),
        "subagent_turns_seen": bool(sub),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="report model families used in this session")
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--transcript", default=None, help="explicit JSONL path")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--require-distinct", action="store_true",
                    help="exit 1 unless a sub-agent ran on a family the main thread did not")
    a = ap.parse_args(argv)

    path = Path(a.transcript) if a.transcript else find_transcript(a.session_id)
    if path is None or not path.is_file():
        out = {"error": "transcript not found", "has_distinct": False,
               "subagent_turns_seen": False}
        print(json.dumps(out, indent=2) if a.json else
              "transcript not found — cannot confirm which models ran")
        # Unknown is not "fine". A caller asking --require-distinct is asking for proof.
        return 1 if a.require_distinct else 0

    res = verdict(scan(path))
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"main thread : {', '.join(res['main_families']) or '-'}")
        print(f"sub-agents  : {', '.join(res['subagent_families']) or '-'}")
        if res["distinct_subagent_families"]:
            print(f"distinct    : {', '.join(res['distinct_subagent_families'])}")
        elif res["subagent_turns_seen"]:
            print("distinct    : none — every sub-agent ran on the main thread's family")
        else:
            print("distinct    : no sub-agent turns recorded")
    if a.require_distinct and not res["has_distinct"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
