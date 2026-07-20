---
name: pr-sanitize
description: "PR body / commit body sensitive-information scrubber. Loads packages/shared-patterns/patterns.json, applies regex + entropy detectors, and produces sanitized text before publishing to GitHub or Jira."
type: skill
---

# PR Sanitize

Scrub any string that will be published externally (PR body, squash commit
body, Jira comment) before it leaves the local machine.

This skill exists because Phase 1's sensitive-filter MCP servers protect
*incoming* data (Jira → LLM, code → LLM). Phase 7 needs the same protection
on *outgoing* data (LLM → GitHub, LLM → Jira).

---

## 1. Inputs

- `text`: the string to be published.
- `context`: short label, used only in logs and warnings. E.g.
  `"pr_body"`, `"squash_commit_body"`, `"jira_comment"`.

## 2. Outputs

```jsonc
{
  "ok": true | false,
  "text": "<sanitized string>",
  "scan_result": "CLEAN" | "REDACTED" | "BLOCKED",
  "redacted_count": N,
  "redacted_patterns": ["..."],   // pattern IDs only, never the matched values
  "blocked_patterns": ["..."],
  "warnings": ["..."]
}
```

- `ok = true` when the text is safe to publish as `text`.
- `ok = false` when `scan_result == "BLOCKED"` — the caller must abort and
  surface the problem to the user.

---

## 3. Procedure

### 3.1 Locate patterns.json

```
candidates = [
  os.environ.get("PATTERNS_PATH"),
  "<plugin_root>/patterns.json",                                # bundled copy — present in marketplace installs (packages/ is dev-only)
  "<repo_root>/packages/shared-patterns/patterns.json",         # dev source-tree copy
  "<plugin_root>/../../packages/shared-patterns/patterns.json",
]
patterns_path = first existing candidate
if patterns_path is null:
  return { ok: false, scan_result: "BLOCKED",
           blocked_patterns: ["patterns_file_missing"],
           text: "" }
```

This mirrors the fail-safe in the Go and TS filter engines: when the policy
file is unavailable, we do NOT publish.

### 3.2 Run the scan

```
patterns = load patterns.json
```

For each pattern:

- `type: regex` (default): apply `regex` against `text`, collect (start, end, pattern_id).
- `type: entropy`: tokenize `text` on whitespace + delimiters, exclude tokens
  matching `exclude_patterns`, and report tokens of length in
  `[min_length, max_length]` whose Shannon entropy ≥ `threshold`.

### 3.3 Classify

```
blocking = matches whose action == "block"
redacting = matches whose action == "redact"
warning   = matches whose action == "warn"

if blocking is non-empty:
  scan_result = "BLOCKED"
  text = ""       # never return the original on block
  blocked_patterns = unique(blocking[].pattern_id)
elif redacting is non-empty:
  scan_result = "REDACTED"
  text = original text with each redacting range replaced by
         "[REDACTED:{pattern_id}]" (outer-wins on overlap)
  redacted_patterns = unique(redacting[].pattern_id)
else:
  scan_result = "CLEAN"
  text = original text

warnings = [ "warn:" + p for p in unique(warning[].pattern_id) ]
ok = (scan_result != "BLOCKED")
```

### 3.4 Logging

Write one line to `{workspace_dir}/logs/pr-sanitize.log` if workspace_dir
is in scope:

```
{ISO ts} ctx={context} result={scan_result} redacted={N} blocked={N}
  patterns_redacted={ids} patterns_blocked={ids}
```

Never log the raw matched values.

---

## 4. Caller obligations

The caller (Orchestrator §4 PR creation, /merge §3 squash body, /work review
cycle) must:

1. Pass the entire string in one call. Do not concatenate then publish
   without re-scanning.
2. On `ok = false`, immediately stop the publishing action and report to
   the user. Suggested message:
   > Sensitive content detected in {context}; cannot publish. Detected patterns: {blocked_patterns}.
   > Edit the source artifact (analysis.md, plan.md, design-v*.md) to remove the
   > value, then re-run the step.
3. On `scan_result = "REDACTED"`, prefer:
   - Going back to the source artifact and removing the value at its origin,
     so the redaction markers don't leak into git history.
   - Falling back to publishing the sanitized text only when the user
     confirms.

---

## 5. Failure modes

| Condition | Behavior |
|-----------|----------|
| patterns.json missing | BLOCKED with `patterns_file_missing`. |
| patterns.json malformed | BLOCKED with `patterns_file_invalid`. |
| One regex fails to compile | Skip that pattern, add `warn:regex_compile_failed:{id}`, continue. |
| `text` empty | CLEAN, empty text, no warnings. |
| `text` larger than 1 MiB | BLOCKED with `payload_too_large`. |

The pattern coverage and replacement format must match Phase 2's TypeScript
filter and Phase 3's Go filter. Drift between the three is a bug — fix
`packages/shared-patterns/patterns.json` rather than tuning this skill.
