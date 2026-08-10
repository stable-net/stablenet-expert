---
description: Read-only diagnosis of the plugin and project environment — reports what is missing and what to fix. It fixes nothing.
argument-hint: "[--project <domain pack id>] [--json]   (both optional — usually run with no arguments)"
allowed-tools: Bash(python3:*), ToolSearch, mcp__plugin_core-dev_stablenet-knowledge__*, mcp__plugin_core-dev_chainbench__*, mcp__plugin_atlassian_atlassian__*
---

# /core-dev:doctor

Read-only environment diagnosis. **It writes nothing** (use `/core-dev:setup` to change things).
It combines a deterministic check (the script) with live MCP probes and reports **READY /
ATTENTION** plus the next action.

---

## 1. Deterministic diagnosis (the script)

```
bash: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py --plugin-root "${CLAUDE_PLUGIN_ROOT}" {--project <id> if given}
```

It reports: active plugin version; project/repo (`git rev-parse`); project_id and the available
packs; `repo_root_env`; env (process plus `.claude/settings*.json`, secrets masked, with
**restart_needed** meaning present in settings but absent from the current env); and
permissions/allowlist. Include this output verbatim in what you report to the user.

## 2. Live MCP probes (this command's own — the §1 script cannot see a real connection)

Load the stablenet-knowledge tools (one ToolSearch call if they are not recognized), then:

- `cks_ops_health` -> status/serviceable, ckg and ckv reachable (+model), **source_root**,
  indexed_head, data_path.
- `cks_ops_freshness` -> indexed_head vs current_head, changed_files.
- **Cross-checks (the important part)**:
  - Is `source_root == §1's repo_root`? If not, **⚠ a different checkout is indexed** — search
    reflects the wrong tree.
  - Is `indexed_head` the current HEAD? If not it is stale (though it may be an *intentional
    base index* — judge only, never reindex).
  - When `data_path` is reachable locally, compare the dataset manifest's (`{parent of
    data_path}/graph-db/manifest.json` and similar) `src_root`/`src_commit` against health's
    `source_root`/`indexed_head`. A difference means **⚠ the config points at a different
    checkout/commit than the index** (the `GO_STABLENET_ROOT` fallback failure mode at config
    creation) -> route to `source_root_mismatch`.
- chainbench: confirm the connection and profile with `chainbench_status` (or a config query).
  Report when not connected (SKIPPED, not blocking).
- jira (only when `requirement_source != "local"`): confirm reachability with a light call.
  Report when not connected.

An unregistered or unreachable MCP is **reported as fact, never treated as blocking**.

## 3. Verdict + next action (remediation)

The **single source for the fix mapping is `doctor.py`'s `REMEDIATION` table**
(ADR [doctor-remediation-adr-2026-06-26](../../docs/adr/ADR-0004-doctor-remediation-routing.md)).
Each entry carries a `klass`: `setup` (our setup.py resolves it), `restart` (session restart),
`manual` (reconfiguration), or `external` (build/install -> docs/SETUP.md).

1. **Show the `remediations` list the §1 script already computed, as it is** — do not rewrite it
   as prose. The script emits it deterministically, so the "next action" section of the doctor
   report *is* that list. For example, on a fresh repo: `setup --fix` (repo_root_env + env),
   `setup --fix --set` (secrets), `setup --autonomous` (allowlist).
2. **The §2 live MCP results are invisible to the script, so route them through the same
   `REMEDIATION` keys** and append them in the same format:
   - stablenet-knowledge not serviceable -> `stablenet_knowledge_not_serviceable` (manual: check
     the server is up, or rewire `STABLENET_KNOWLEDGE_MCP_URL` and restart)
   - `source_root ≠ repo_root` -> `source_root_mismatch` (manual: reconfigure to index the
     current repo, then restart)
   - index stale -> `index_stale` (manual: reindex — ⚠ *not* if it is an intentional base index;
     confirm with the user)
   - MCP unreachable -> `mcp_unreachable` / `stablenet_knowledge_mcp_not_built` /
     `chainbench_not_installed`
3. End by showing the script's **one-line summary** verbatim
   (`READY` / `ATTENTION — N action(s): <command>`).

**Read-only contract**: doctor modifies no file, setting or index — it only *prints* the
remediation, and the user applies it by running the relevant `setup` command.
