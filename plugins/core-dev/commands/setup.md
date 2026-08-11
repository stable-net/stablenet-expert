---
description: Check and register the settings values core-dev uses. Use --uninstall to take them back.
argument-hint: "[--check | --fix | --uninstall] [--yes] [--scope user|project] [--repo <path>]   (checks only when omitted)"
---

# /core-dev:setup

So that `core-dev` works straight after installation: **check** whether the environment values
the plugin's MCP servers (`.mcp.json`) require are registered, and fill in what is missing —
**detected automatically, or asked for when detection fails**.

- Paths and public values -> **`env` in `~/.claude/settings.json`** (user scope, the default).
  These describe the machine (one checkout, one server), so there is no reason to re-enter them
  per project. With `--scope project` they go to `{repo_root}/.claude/` instead — for a shared
  machine, or where the global file must not be touched.
- Secrets -> `{repo_root}/.claude/settings.local.json` (gitignored automatically). There are no
  secret entries at present: Jira authenticates over OAuth and Claude Code holds the credentials
  (ADR-0013).
- **The active domain pack's `repo_root_env` (e.g. `GO_STABLENET_ROOT`) -> written to
  `settings.json` as the current repo root** (when run from inside it; pass `--project <id>` if
  the project_id is ambiguous).
- **`--autonomous`**: registers a granular `permissions.allow` (plugin MCP + read-only bash +
  the pipeline's write path: Write/Edit, go/make builds, feature-branch git, gh pr create) and
  `permissions.deny` (blocking Read of `.env*`, `.secrets`, `settings.local.json`) in
  `settings.local.json` — opt-in, for running without prompts. merge/tag/release are not on the
  allowlist: the `/core-dev:merge` gate and the git-guard hook stay in force.
- **`--uninstall`**: takes back what `--fix` wrote. Every write records the key **and the value**
  in a manifest (`.claude/.stablenet-expert-managed.json`), so **only entries whose value is
  unchanged** are removed. A value the user edited later is kept and reported — undoing
  somebody's edit is worse than leaving a stale key (ADR-0018). It is a dry run by default;
  `--yes` makes it act. Run it **before** removing the plugin: once
  `claude plugin uninstall` finishes, the script that knows which entries were this plugin's is
  gone with it.
- **`--repo <path>`**: names the target project. The default is the git root of the current
  directory, so without this flag the command must run inside the project. Use it to run from
  anywhere — without it, a run started elsewhere cleans only the user scope and leaves the
  project keys quietly in place.

What is checked: `STABLENET_KNOWLEDGE_MCP_URL` and `CHAINBENCH_DIR`; the Atlassian MCP plugin
(installed and authenticated); plus advisories for `chainbench-mcp` on PATH and for
`permissions`.

`${CLAUDE_PLUGIN_ROOT}/scripts/setup.py` does the actual checking and writing (stdlib only).

---

## 0. Arguments (pass the user's flags straight through to setup.py)
- Default (no arguments): check (equivalent to `--check`), then offer and perform §2's
  registration for anything outstanding.
- `--check`: check only, write nothing.
- `--fix`: write env into settings.json (including the active pack's `repo_root_env` — skipped
  as MISMATCH when the cwd is the plugin repo).
- `--autonomous`: register the granular allow/deny (**works without `--fix`**).
- `--project <id>`: name the active domain pack when auto-detection is ambiguous.

## 1. Run it (passing the flags)
```
1.1. bash: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup.py {user flags; --check if none}
     # e.g. /core-dev:setup --autonomous       -> setup.py --autonomous (register the allowlist)
     #      /core-dev:setup --fix --autonomous  -> env + repo_root_env + allowlist
1.2. Show the user the output table and the write results as-is (KEY/STATUS/SOURCE).
1.3. repo_root_env reported as **MISMATCH** -> say: "this is the plugin repo, so repo_root_env
     was not written -- run setup from the root of the target project (e.g. go-stablenet)."
1.4. exit 0 with everything resolved (and no --fix/--autonomous) -> finish:
     "Everything is already configured." Anything MISSING -> §2.
```

## 2. Handle what is outstanding (detect, then ask)
```
2.1. With MISSING entries, first write only what detection or the existing env can supply:
     bash: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup.py --fix
     (Merges detected/env path values into .claude/settings.json. Existing values are kept.)

2.2. For whatever is still MISSING (typically a path detection could not find):
     Ask the user for each value (warning them not to put a secret on screen).
     Re-run with what they give:
     bash: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup.py --fix \
             --set KEY1=VALUE1 --set KEY2=VALUE2 ...
     # Should a secret entry ever exist, pass it through --set -- the script writes it to
     #   settings.local.json and adds .claude/settings.local.json to .gitignore.
     # If the user would rather fill it in themselves in a terminal, point them at:
     #   `! python3 .../setup.py --fix --interactive`

2.3. Re-check:
     bash: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup.py --check
     Still MISSING -> report what is missing and why, and give the install/build route for it
     from docs/SETUP.md (e.g. building stablenet-knowledge-mcp, installing chainbench).
```

## 3. Closing notes
```
3.1. Once written:
     - "Registered in settings.json/settings.local.json. Restart the session so the MCP servers
        read the new env (exit -> claude --continue). /reload-plugins does not restart MCP."
     - If chainbench-mcp is not on PATH, give its install route.
     - `--fix` **writes the active pack's repo_root_env (e.g. `GO_STABLENET_ROOT`) as the current
       repo root** -- it would also flow from `git rev-parse`, but making it explicit removes the
       ambiguity. Pass `--project <id>` when the project_id is unclear.
     - For prompt-free runs, `--autonomous` registers a granular allow (plugin MCP + read-only
       bash + Write/Edit, builds, feature-branch git) and deny (blocking Read of secrets).
       merge/tag still prompt (or go through `/core-dev:merge`). Going prompt-free across every
       other tool means the user setting `permissions.defaultMode` themselves -- this never sets
       it, for security.
```

## 4. Done when (checklist)
- [ ] The setup.py --check table shown to the user
- [ ] Values available from detection or the existing env merged into .claude/settings.json via
      --fix (existing values preserved)
- [ ] Values that could not be found asked for and written via --set (secrets to
      settings.local.json + .gitignore)
- [ ] Re-checked to confirm; anything left gets its install/build route
- [ ] Session restart explained (so MCP picks up the env)
