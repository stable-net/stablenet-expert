---
description: Start work from a requirement you write yourself — analysis, design, implementation, verification, through to a PR. Works without Jira.
argument-hint: "\"<a sentence or two on what to build or fix>\"  [--type feature|bugfix|code_review|release] [--auto-merge]"
allowed-tools: Read, Write, Edit, Bash, Agent, TodoWrite, mcp__plugin_core-dev_stablenet-knowledge, mcp__plugin_core-dev_chainbench, mcp__plugin_atlassian_atlassian
---

# /core-dev:work-with-prompt

Start the automation pipeline from **free-text requirements**, with no Jira ticket. It runs the
same pipeline as `/core-dev:work-with-jira` (planner -> implementer -> evaluator); only the entry
point differs. Internally the requirement is synthesized into a `ticket.json`, so the existing
`template-parse` + Orchestrator path is reused unchanged (`requirement_source: "local"`).

> Autonomous entry: this command raises **no user prompts** for Jira, duplicates or sensitive
> data. Every run is a fresh `LOCAL-{timestamp}` job, and local secrets are auto-redacted rather
> than blocking.

---

## 0. Argument shape

- e.g. `/core-dev:work-with-prompt "fix the nil pointer panic in consensus Finalize"`
- Type hint (optional): `... --type bugfix` (inferred from the text when omitted)
- Auto-merge (optional): `... --auto-merge` — carry on past PR creation through merge/tag/push.
  **Off by default** (the merge/push/tag gates stay). Even when on, merge.md §3's safety
  conditions (APPROVED/CI/MERGEABLE) still hold.

---

## 1. Validate the argument

```
1.1. Parse
   - the quoted requirement body -> requirement_text
   - --type <feature|bugfix|code_review|release> -> type_hint (optional)
   - --auto-merge (flag) -> auto_merge_flag = true (default false)
   - empty requirement -> print usage and stop:
     "usage: /core-dev:work-with-prompt \"<requirement text>\" [--type <type>] [--auto-merge]"
```

---

## 2. Check for .stablenet-expert/

```
2.1. Find the project root
   bash: git rev-parse --show-toplevel
   failure -> "not a git repository. Run this inside the go-stablenet checkout." -> stop
   success -> keep as repo_root
2.2. bash: mkdir -p {repo_root}/.stablenet-expert/tickets
```

---

## 3. Create the job directory (always new)

```
3.1. bash: date -u +"%Y%m%d_%H%M%S"  -> timestamp
3.2. local_id = "LOCAL-{timestamp}"
3.3. workspace = "{repo_root}/.stablenet-expert/tickets/{local_id}"
3.4. bash: mkdir -p {workspace}/logs
```

There is no duplicate/resume check: local_id is unique per run, so every run is a new job and
nothing needs asking.

---

## 4. Requirement intake -> synthesize ticket.json

The model synthesizes the free text into a structure `template-parse` can read.

```
4.1. Decide work_type
   Use type_hint when given. Otherwise infer from requirement_text:
     - centred on "bug/panic/error/fix/broken/failing" -> bugfix
     - centred on "review" -> code_review
     - centred on "release/tag/version" -> release
     - otherwise (new behaviour, feature, improvement) -> feature

4.2. Synthesize the description (markdown)
   Build the body from headers template-parse recognizes. Where a section is empty, fill it in
   by inference, but leave anything you are not confident about blank so it surfaces in
   missing_fields:

   - first line, always:  "## Work Type: {work_type}"
   - feature:     ## Summary / ## Background / ## Requirements (checklist) / ## Scope (modules) /
                  ## Acceptance Criteria
   - bugfix:      ## Summary / ## Steps to Reproduce / ## Expected Behavior / ## Actual Behavior /
                  ## Scope (modules, severity) / ## Acceptance Criteria
   - code_review: ## Summary / ## Review Target / ## Review Criteria
   - release:     ## Summary / ## Version / ## Changes / ## Release Checklist

   These are the English half of template-parse §3.1/§3.2's header table; it matches Korean and
   English alike, so a ticket written either way still parses.

   Reflect requirement_text faithfully and keep go-stablenet domain terms as they are.
   (Leave the scope modules blank rather than guessing -- the planner works them out precisely
   through stablenet-knowledge.)

4.3. Scan for local secrets (auto-redact, never a hard stop)
   Where requirement_text carries an obvious secret (an API key, token, password, `sk-`,
   `ghp_`, `-----BEGIN`, ...), replace the value in the description with "[REDACTED]" and count it.
     scan_result = (anything replaced) ? "REDACTED" : "CLEAN"   # never BLOCKED, never stops

4.4. Write ticket.json ({workspace}/ticket.json)
   {
     "ticket_id": "{local_id}",
     "type": "{work_type}",
     "summary": "<one-line summary>",
     "description": "<the markdown synthesized in 4.2>",
     "requirement_source": "local",
     "_filter_metadata": { "scan_result": "{scan_result}", "redacted_count": N }
   }
```

---

## 5. Identify ticket_type + initialize state.json

```
5.1. Call the template-parse skill
   input: ticket.description (the markdown from 4.2), summary: ticket.summary
   output: { work_type, summary, pipeline_variant, fields, missing_fields, warnings }
   Save it as {workspace}/ticket-parsed.json.
   (Where work_type disagrees with the intake inference, template-parse wins.)

5.2. missing_fields is not a reason to stop
   Proceed even when it is non-empty -- the planner fills the gaps from stablenet-knowledge
   during ANALYSIS, with no prompting.

5.3. Initialize state.json
   base_ref = bash: git rev-parse HEAD    # the commit checked out now is this ticket's base --
                                          # no later stage may checkout/pull another branch and
                                          # move it
   state-machine.init_state(
     ticket_id={local_id},
     ticket_type={work_type},
     workspace_dir={workspace},
     pipeline_variant={pipeline_variant},
     requirement_source="local",
     base_ref={base_ref}
   )
   # With requirement_source="local", autonomy derives as {mode:auto, on_blocked:escalate,
   # auto_merge:false}. When --auto-merge was given, overwrite
   # state.config.autonomy.auto_merge = true after init_state (releasing the merge/tag/push
   # gates; merge.md §3's safety conditions still apply). Left unset it is false -- autonomous
   # as far as the PR and no further.

5.4. Record TICKET_INTAKE.sensitive_check
   states.TICKET_INTAKE.sensitive_check = {
     "result": "{scan_result}",        # CLEAN | REDACTED (local scan)
     "redacted_count": N,
     "scanned_at": "{ISO now}"
   }
```

---

## 6. Dispatch the Orchestrator agent

```
6.1. Agent(
       subagent_type="orchestrator",
       description="Run core-dev pipeline for {local_id} (local requirement)",
       prompt="workspace_dir={workspace}\nmode=fresh"
     )
6.2. On completion, print:
   "Started work from a free-text requirement. workspace: {workspace}
    (requirement_source=local -- runs to PR creation with no Jira sync; merge is separate,
     via /core-dev:merge)"
```

---

## 7. Done when (checklist)

- [ ] Empty requirement prints usage
- [ ] A clear error outside a git repository
- [ ] A unique LOCAL-{timestamp} job directory per run (no duplicate/resume prompt)
- [ ] Free text synthesized into a ticket.json using template-parse's headers
- [ ] Local secrets auto-redacted (no BLOCKED hard stop)
- [ ] state.json initialized with requirement_source="local"
- [ ] Orchestrator runs the pipeline with no Jira calls (autonomous to PR creation; merge gate held)
