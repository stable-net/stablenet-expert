---
description: Squash-merge an approved PR, transition Jira to Complete, and clean up the local branch.
argument-hint: "<JIRA-ID, e.g., STABLE-1234>"
---

# /stablenet-core-dev:merge

Squash-merge a PR that has passed code review, then close the loop on
Jira and the local workspace.

This command is the only one in the plugin that touches `main`, so the
preconditions are strict and every external action is logged.

The §3 preconditions (PR APPROVED + required checks green + MERGEABLE) are a
HARD safety gate and are **never** bypassed — not even when
`state.config.autonomy.auto_merge == true`. auto_merge only governs whether the
pipeline reaches this command without a human typing `/stablenet-core-dev:merge` and
whether sanitize REDACTED prompts (§4.3); it never relaxes the merge safety checks.

---

## 1. Argument validation

```
1.1. Require <JIRA-ID> matching /^[A-Z]+-\d+$/. Print usage on miss:
     "Usage: /stablenet-core-dev:merge STABLE-1234"
1.2. Resolve repo root:
     bash: git rev-parse --show-toplevel → repo_root
     If not a git repo → abort with clear message.
```

---

## 2. Locate the workspace + PR

```
2.1. Find the most-recent ticket workspace:
     scan {repo_root}/.stablenet-expert/tickets/{jira_id}_*  (timestamp desc)
     Take the first whose state.current_state is in {"COMPLETION","COMPLETED"}.
     If none exists, abort:
       "No COMPLETION-stage workspace found for {jira_id}.
        Run /stablenet-core-dev:work to create a PR first."

2.2. Read workspace/state.json → state
     pr_url = state.states.COMPLETION.pr_url
     If pr_url is empty:
       "This ticket does not have a PR recorded.
        Run /stablenet-core-dev:work to complete the pipeline first."

2.3. Extract PR number from pr_url (regex /pull/(\d+)).
     branch = state.states.IMPLEMENTATION.branch
```

---

## 3. Precondition checks (must all pass)

Each check writes to `{workspace}/logs/merge-precheck.log`. Any failure
aborts before touching `main`.

```
3.1. gh CLI authentication
     bash: gh auth status
     If not authenticated: abort with hint "Run gh auth login".

3.2. PR exists and is open
     bash: gh pr view {pr_number} --json state,reviewDecision,mergeable,statusCheckRollup
     Parse JSON.
     If pr.state != "OPEN": abort with state value
       (MERGED → "Already merged."; CLOSED → "PR was closed without merging.").

3.3. Review approval
     If pr.reviewDecision != "APPROVED":
       abort:
         "PR is not approved (state: {reviewDecision}). Required: APPROVED."
         If reviewDecision == "CHANGES_REQUESTED":
           hint: "Run /stablenet-core-dev:review {pr_url} to address feedback."

3.4. Required status checks
     For each check in pr.statusCheckRollup:
       if check.status != "COMPLETED" or check.conclusion not in {"SUCCESS","NEUTRAL","SKIPPED"}:
         add to failing_checks
     If failing_checks is non-empty:
       abort listing the failing checks ("ci/build", "ci/test", …).

3.5. Mergeable
     If pr.mergeable != "MERGEABLE":
       abort with the value (CONFLICTING → "Resolve conflicts on the branch.";
                              UNKNOWN → "GitHub is still computing mergeability; retry.").
```

If any check aborts, print a one-line summary at the top and the per-check
details below. Do not touch git state.

---

## 4. Assemble the squash commit body

```
4.1. Read the ticket and plan progress
     read workspace/ticket.json → ticket
     plan_progress = state.states.IMPLEMENTATION.plan_progress
     commits = flatten(plan_progress.steps[*].commits)

4.2. Build the body using the size-aware strategy (RI-14)

     # Two-tier formatter
     if plan_progress.total_steps <= 10:
       body = "{ticket_id}: {ticket.summary}\n\n"
       for each step in plan_progress.steps:
         for hash in step.commits:
           subject = bash: git -C {repo_root} log -1 --format=%s {hash}
           body += "* " + subject + "\n"
     else:
       # Category bucketing
       buckets = group steps by category derived from description:
                 (interface|api|type|signature) → "Interface changes"
                 (impl|logic|finalize|...) → "Implementation"
                 (test|fixture|race|integration) → "Tests"
                 (doc|godoc|changelog|comment) → "Docs"
                 default → "Misc"
       body = "{ticket_id}: {ticket.summary}\n\n"
       for each bucket name in [Interface, Implementation, Tests, Docs, Misc]:
         steps_in = bucket[name]
         if steps_in is empty: continue
         total_commits = sum(len(step.commits) for step in steps_in)
         body += f"* {name} ({total_commits} commits)\n"
         for step in steps_in:
           body += "  - {step.description}\n"

     body += "\nJira: {JIRA_BASE_URL}/browse/{ticket_id}\n"
     body += "PR: #{pr_number}\n"

4.3. Sanitize before publishing (P7-7)
     result = pr-sanitize.scan(text=body, context="squash_commit_body")
     if not result.ok:
       abort with the pr-sanitize block message; do NOT continue to merge.
     if result.scan_result == "REDACTED":
       if state.config.autonomy.auto_merge == true:
         continue — redaction is already applied to body (no prompt).
       else:
         confirm with the user before continuing (prefer source fixes per the
         pr-sanitize caller guidance).
     body = result.text
```

---

## 5. Execute the squash merge

```
5.1. Use gh, not raw git, so GitHub branch protections are honored.
     subject = "{ticket_id}: {ticket.summary}"
     # Also sanitize the subject just in case.
     subject = pr-sanitize.scan(text=subject, context="squash_commit_subject").text

     bash: gh pr merge {pr_number} --squash --delete-branch \
       --subject "{subject}" \
       --body  "$(cat <<'PR_BODY_EOF'
{body}
PR_BODY_EOF
)"

5.2. Capture the merge commit hash
     bash: gh pr view {pr_number} --json mergeCommit -q '.mergeCommit.oid' → merge_hash
     If merge_hash is empty (GitHub eventual consistency):
       sleep 3, retry up to 3 times.

5.3. Log success
     append to {workspace}/logs/merge.log:
       "{ts} merge ok pr=#{pr_number} hash={merge_hash}"
```

If `gh pr merge` exits non-zero, the merge did NOT happen. Surface the gh
output and abort — do not perform the post-merge steps in §6.

---

## 6. Post-merge cleanup (Phase 7 §6)

Each step is best-effort and never reverses the merge. Failures here become
warnings — the user keeps the merged code either way.

```
6.1. Jira: status → Complete
     mcp__plugin_stablenet-core-dev_jira-gateway__jira_update_status(ticket_id, "Complete")
     On failure: print warning + suggestion to update Jira manually.

6.2. Jira: comment with the merge hash
     comment_body = "Merged. Commit: {merge_hash}\nBranch: {branch} (deleted)"
     # Sanitize the comment too.
     result = pr-sanitize.scan(text=comment_body, context="jira_merge_comment")
     mcp__plugin_stablenet-core-dev_jira-gateway__jira_add_comment(ticket_id, result.text)

6.3. Local branch sync
     # default_branch = the repo's actual default (origin/HEAD) — never assume "main"
     bash: default_branch=$(git -C {repo_root} symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||'); [ -n "$default_branch" ] || default_branch=main
     bash: git -C {repo_root} checkout {default_branch}
     bash: git -C {repo_root} pull --ff-only origin {default_branch}
     # The remote branch is already deleted by --delete-branch. The local
     # branch may linger; remove it only if it's fully merged into the default branch.
     bash: git -C {repo_root} branch --merged {default_branch} | grep -E "^\s*{branch}\s*$" \
           | xargs -r git -C {repo_root} branch -d
     If a manual unmerged version remains, leave it alone — never use
     `git branch -D` on someone's local work.

6.4. state.json finalize
     state.states.COMPLETION.status     = "completed"
     state.states.COMPLETION.merged_at  = ISO now UTC
     state.states.COMPLETION.merge_commit = merge_hash
     state.current_state = "COMPLETED"
     write state.json
```

---

## 7. Output

```
✓ Merged STABLE-1234
  PR:    {pr_url}
  Commit: {merge_hash}
  Branch: {branch} (deleted)
  Jira:   {ticket_id} → Complete
```

On abort, output the precondition table with PASS/FAIL per check and the
first failing check's detail line. Suggest the next concrete action
(e.g., "Run /stablenet-core-dev:review to address review comments.").

---

## 8. Safety policies

- The squash merge is the only place this plugin touches `main`. Aborts
  must be loud; success messages must be terse.
- Never bypass branch protections: use `gh pr merge`, never raw
  `git merge` or `git push origin main`.
- Never `--no-verify` or use `--admin` to override checks.
- Never `git branch -D` on anything other than this ticket's feature branch,
  and only when `git branch --merged` confirms it's fully merged.
- Never re-run `gh pr merge` after a partial failure without first
  re-checking pr.state via `gh pr view` — the merge may have actually
  succeeded server-side.
- All Jira and gh API calls write to `{workspace}/logs/merge.log` so the
  user can audit the run.
