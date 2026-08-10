---
description: Show how far a job has got and whether anything is stuck.
argument-hint: "[Jira ticket number]   (omit for every job in progress)"
---

# /core-dev:status

Report job status.

---

## 1. Branch on the argument

```
1.1. Empty -> all-active mode (go to step 3)
1.2. JIRA-ID shape (/^[A-Z]+-\d+$/) -> single-ticket mode (go to step 2)
1.3. Neither -> print usage and stop:
   "usage: /core-dev:status [JIRA-ID]
    e.g.: /core-dev:status STABLE-1234
    omitted: every active job"
```

---

## 2. Single-ticket detail mode

```
2.1. Find the project root
   bash: git rev-parse --show-toplevel -> repo_root

2.2. Look for the job directory
   bash: ls -d {repo_root}/.stablenet-expert/tickets/{jira_id}_* 2>/dev/null | sort -r

   Nothing -> print "No job for {jira_id}." + stop
   Something -> take the newest (workspace)

2.3. Load state.json
   read {workspace}/state.json -> state

2.4. Work out the last activity time
   Take the most recent started_at or completed_at across the states object.
   In IMPLEMENTATION, plan_progress.steps[*].last_checkpoint.at is a candidate too.

2.5. Collect the artifact list
   bash: ls {workspace} | grep -v "^logs$"

2.6. Step progress, in IMPLEMENTATION
   IF state.current_state == "IMPLEMENTATION":
     walk state.states.IMPLEMENTATION.plan_progress.steps:
       status == "completed"   -> "✓"
       status == "in_progress" -> "◐"
       status == "pending"     -> "○"
       status == "failed"      -> "✗"

     in_progress with a last_checkpoint:
       show the checkpoint (work_in_progress, uncommitted_files)

2.7. Output format
   Print in this shape:

   ┌─ {ticket_id} ──────────────────────────────────────┐
   │ State:        {current_state}                       │
   │ Agent:        {current_agent || "—"}                │
   │ Workspace:    {workspace (basename)}                 │
   │ Created:      {created_at}                          │
   │ Last activity:{last_activity}                       │
   │ Branch:       {state.states.IMPLEMENTATION.branch || "—"} │
   │                                                      │
   │ Failures:     {failure_summary.total_failures}       │
   │   by_state:   {by_state}                            │
   │   by_type:    {by_type}                             │
   │   patterns:   {number of recurring_patterns}        │
   │                                                      │
   │ Artifacts:                                           │
   │   - ticket.json                                      │
   │   - analysis.md                                      │
   │   - plan.md                                          │
   │   - design-v2.md                                     │
   │                                                      │
   │ Plan Progress (when in IMPLEMENTATION):              │
   │   [1] ✓ add the interface (commit: a1b2c3d)          │
   │   [2] ◐ implement the logic                          │
   │       checkpoint: 70% done, edge cases outstanding   │
   │       uncommitted: consensus/wbft/finalize.go        │
   │   [3] ○ add tests                                    │
   │   [4] ○ integration test                             │
   │   [5] ○ update the docs                              │
   │                                                      │
   │ PR:           {COMPLETION.pr_url || "—"}            │
   └──────────────────────────────────────────────────────┘

2.8. Mention other directories for the same ticket
   When the same ticket_id has several directories (a rework history):
     "This ticket has {N} earlier job director(ies)."
```

---

## 3. All-active mode

```
3.1. Find the project root
   bash: git rev-parse --show-toplevel -> repo_root

3.2. Scan the job directories
   bash: ls -d {repo_root}/.stablenet-expert/tickets/*_* 2>/dev/null

3.3. Load each state.json and filter
   for each folder:
     read {folder}/state.json
     active when: current_state not in ["COMPLETED"]
     active -> append to active_workspaces

3.4. Nothing active
   IF active_workspaces.empty:
     print "No active jobs." and stop

3.5. Sort newest first
   active_workspaces.sort by state.created_at DESC

3.6. Output format (summary)
   One line each:

   Active jobs ({N}):

   {ticket_id}  {current_state}  {last_activity}  {failure_summary.total_failures} failure(s)
   ────────────  ──────────────  ──────────────  ──────────────
   STABLE-1234  IMPLEMENTATION  2026-05-28 01:30  1 failure
   STABLE-1230  EVALUATION      2026-05-27 14:20  0
   STABLE-1228  BLOCKED         2026-05-26 10:15  3 failures  ⚠

   Detail: /core-dev:status <JIRA-ID>

3.7. Call out BLOCKED jobs
   When any job is BLOCKED, give it its own section:

   ⚠ BLOCKED jobs ({N}) - manual intervention needed:
     STABLE-1228:
       failures: 3 (max_eval_cycles exceeded)
       recurring: {first recurring_patterns entry}
       last activity: 2026-05-26 10:15
```

---

## 4. Error handling

| Scenario | Handling |
|---------|------|
| No .stablenet-expert/ | print "The coding agent has not been used here yet." |
| Corrupt state.json (JSON parse failure) | skip that directory, carry on with the rest, warn |
| Partial ticket_id match | exact matches only (STABLE-12 does not match STABLE-123) |

---

## 5. Done when (checklist)

- [ ] Single-ticket detail printed (state, artifacts, failure history, plan_progress)
- [ ] Per-step progress (✓/◐/○/✗) plus checkpoint during IMPLEMENTATION
- [ ] All-active list printed (summary form, newest first)
- [ ] A clear message when nothing is active
- [ ] BLOCKED jobs called out separately
- [ ] Multiple job directories for one ticket are mentioned
- [ ] Corrupt state.json handled gracefully
