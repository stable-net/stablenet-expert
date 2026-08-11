---
description: Squash-merge an approved PR, move the Jira ticket to Complete, and tidy up the branches. The only command that touches main.
argument-hint: "<Jira ticket number> or <PR URL>   (e.g. STABLE-1234 / https://github.com/o/r/pull/456)"
---

# /core-dev:merge

Squash-merge a PR that has passed code review, then finish up in Jira and in the local
workspace.

This is the only command in the plugin that touches `main`, so its preconditions are strict and
every outward action is logged.

§3's preconditions (PR APPROVED + required checks green + MERGEABLE) are a **hard** safety gate
and are **never** bypassed, not even when `state.config.autonomy.auto_merge == true`. What
auto_merge controls is only (1) whether the pipeline can reach this command without a person
typing `/core-dev:merge`, and (2) whether the sanitize REDACTED prompt is handled (§4.3) — it
never relaxes a merge safety check.

---

## 1. Validate the argument

```
1.1. The argument is one of two things, and which one decides the mode.

     (a) Jira ticket number  — /^[A-Z]+-\d+$/          -> ticket mode
     (b) PR URL              — /github\.com/.+/pull/\d+/ -> PR mode

     Neither -> print usage:
       "usage: /core-dev:merge STABLE-1234
               or    /core-dev:merge https://github.com/<owner>/<repo>/pull/456"

     Both modes clear §3's safety preconditions (approval, CI, mergeable) **identically**. All
     that differs is how the PR is found and what can be recorded after the merge.
1.2. Find the repo root:
     bash: git rev-parse --show-toplevel -> repo_root
     Not a git repository -> stop with a clear message.
```

---

## 2. Find the workspace and the PR

**PR mode skips 2.1-2.3 and uses only 2.0.** Having no workspace is the premise of that mode —
there is no guarantee this PR came out of this pipeline.

```
2.0. (PR mode) Take it straight from the PR URL
     pr_number = /pull/(\d+) from the URL
     bash: gh pr view {pr_number} --json headRefName,title,body,url
     branch = headRefName
     jira_id = extracted per the `jira-via-atlassian` skill §4 (branch name -> PR body). On
               failure, skip the Jira update **without asking** -- the merge itself does not
               depend on a ticket.
     -> go to step 3

2.1. (ticket mode) Find the most recent workspace for the ticket:
     Scan {repo_root}/.stablenet-expert/tickets/{jira_id}_* (newest timestamp first).
     Take the first whose state.current_state is in {"COMPLETION","COMPLETED"}.
     None -> stop:
       "No COMPLETION-stage workspace found for {jira_id}.
        Create the PR first with /core-dev:work-with-jira."

2.2. Read workspace/state.json -> state
     pr_url = state.states.COMPLETION.pr_url
     Empty pr_url:
       "This ticket has no recorded PR.
        Complete the pipeline first with /core-dev:work-with-jira."

2.3. Extract the PR number from pr_url (regex /pull/(\d+)).
     branch = state.states.IMPLEMENTATION.branch
```

---

## 3. Preconditions (all must pass)

Each check is written to `{workspace}/logs/merge-precheck.log`. A single failure stops the run
before `main` is touched.

```
3.1. gh CLI authentication
     bash: gh auth status
     Unauthenticated -> stop, pointing at `gh auth login`.

3.2. The PR exists and is open
     bash: gh pr view {pr_number} --json state,reviewDecision,mergeable,statusCheckRollup
     Parse the JSON.
     pr.state != "OPEN" -> stop, naming the state
       (MERGED -> "already merged."; CLOSED -> "the PR was closed without merging.").

3.3. Review approval
     pr.reviewDecision != "APPROVED" ->
       stop:
         "The PR is not approved (state: {reviewDecision}). Required: APPROVED."
         reviewDecision == "CHANGES_REQUESTED" ->
           hint: "Run /core-dev:review-jira {jira_id} to apply the feedback."

3.4. Required status checks
     For each check in pr.statusCheckRollup:
       check.status != "COMPLETED", or
       check.conclusion not in {"SUCCESS","NEUTRAL","SKIPPED"} ->
         add to failing_checks
     failing_checks non-empty ->
       stop, listing the failed checks ("ci/build", "ci/test", ...).

3.5. Mergeability
     pr.mergeable != "MERGEABLE" ->
       stop, naming the value (CONFLICTING -> "resolve the conflicts on the branch.";
                                UNKNOWN -> "GitHub is still computing mergeability. Retry.").
```

On any stop, print a one-line summary first, then the per-check detail below it. Leave the git
state untouched.

---

## 4. Assemble the squash commit body

**PR mode**: with no workspace there is no plan progress to synthesize a body from, so use the
PR's own title and body (already fetched via `gh pr view`). §4.3's sanitize runs in **both**
modes — wherever the body came from, what gets published is the same.

```
4.1. Read the ticket and the plan progress
     read workspace/ticket.json -> ticket
     plan_progress = state.states.IMPLEMENTATION.plan_progress
     commits = flatten(plan_progress.steps[*].commits)

4.2. Write the body, strategy by size

     # 2-tier formatter
     plan_progress.total_steps <= 10:
       body = "{ticket_id}: {ticket.summary}\n\n"
       for each step in plan_progress.steps:
         for each hash in step.commits:
           subject = bash: git -C {repo_root} log -1 --format=%s {hash}
           body += "* " + subject + "\n"
     otherwise:
       # bucket by category
       Group steps by a category inferred from the description:
                 (interface|api|type|signature) -> "Interface changes"
                 (impl|logic|finalize|...) -> "Implementation"
                 (test|fixture|race|integration) -> "Tests"
                 (doc|godoc|changelog|comment) -> "Docs"
                 default -> "Misc"
       body = "{ticket_id}: {ticket.summary}\n\n"
       For each bucket name in [Interface, Implementation, Tests, Docs, Misc]:
         steps_in = bucket[name]
         steps_in empty -> skip
         total_commits = sum(len(step.commits) for step in steps_in)
         body += f"* {name} ({total_commits} commits)\n"
         for each step in steps_in:
           body += "  - {step.description}\n"

     body += "\nJira: {jira_site_url}/browse/{ticket_id}\n"   # site URL from cloudId resolution
     body += "PR: #{pr_number}\n"

4.3. Sanitize before publishing (P7-7)
     result = pr-sanitize.scan(text=body, context="squash_commit_body")
     not result.ok ->
       stop with pr-sanitize's block message; do **not** proceed to merge.
     result.scan_result == "REDACTED" ->
       state.config.autonomy.auto_merge == true ->
         continue -- the redaction is already applied to body (no prompt).
       otherwise ->
         confirm with the user before continuing (per pr-sanitize's caller guidance, which
         prefers fixing the source itself).
     body = result.text
```

---

## 5. Perform the squash merge

```
5.1. Use gh rather than raw git, so GitHub's branch protection is honoured.
     subject = "{ticket_id}: {ticket.summary}"
     # sanitize the subject too, just in case.
     subject = pr-sanitize.scan(text=subject, context="squash_commit_subject").text

     bash: gh pr merge {pr_number} --squash --delete-branch \
       --subject "{subject}" \
       --body  "$(cat <<'PR_BODY_EOF'
{body}
PR_BODY_EOF
)"

5.2. Get the merge commit hash
     bash: gh pr view {pr_number} --json mergeCommit -q '.mergeCommit.oid' -> merge_hash
     Empty merge_hash (GitHub eventual consistency):
       sleep 3s and retry, up to 3 times.

5.3. Success log
     Append to {workspace}/logs/merge.log:
       "{ts} merge ok pr=#{pr_number} hash={merge_hash}"
```

If `gh pr merge` exits non-zero the merge did **not** happen. Surface gh's output and stop — do
not run §6's post-merge steps.

---

## 6. Post-merge cleanup (Phase 7 §6)

**What PR mode skips and what it does not:**

| Step | PR mode |
|---|---|
| 6.1 Jira status -> Complete | done if a jira_id was extracted, skipped otherwise |
| 6.2 Jira comment | same as above |
| 6.3 Local branch sync | **done** -- it has nothing to do with the workspace |
| 6.4 state.json finalization | skipped -- there is no state to update |

**Say explicitly** in §7's output what was skipped. Reporting only "merged" leaves the reader
believing Jira was updated, and the board drifts quietly.

Every step here is best-effort and never undoes the merge. A failure at this point is a warning
only — either way the user still has the merged code.

```
6.1. Jira: status -> Complete
     transition ticket_id to "Complete" via the `jira-via-atlassian` skill §3
     (getTransitionsForJiraIssue -> three-tier match -> transitionJiraIssue)
     On failure: warn and suggest updating Jira by hand.

6.2. Jira: comment with the merge hash
     comment_body = "Merged. Commit: {merge_hash}\nBranch: {branch} (deleted)"
     # sanitize the comment too.
     result = pr-sanitize.scan(text=comment_body, context="jira_merge_comment")
     mcp__plugin_atlassian_atlassian__addCommentToJiraIssue(cloudId, ticket_id, result.text)

6.3. Local branch sync
     # default_branch = the repo's actual default (origin/HEAD) -- never assume "main"
     bash: default_branch=$(git -C {repo_root} symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||'); [ -n "$default_branch" ] || default_branch=main
     bash: git -C {repo_root} checkout {default_branch}
     bash: git -C {repo_root} pull --ff-only origin {default_branch}
     # The remote branch is already gone via --delete-branch. A local branch may remain;
     # remove it only when it is fully merged into the default branch.
     bash: git -C {repo_root} branch --merged {default_branch} | grep -E "^\s*{branch}\s*$" \
           | xargs -r git -C {repo_root} branch -d
     If an unmerged hand-made version survives, leave it alone -- never run `git branch -D`
     on somebody's local work.

6.4. Finalize state.json
     state.states.COMPLETION.status     = "completed"
     state.states.COMPLETION.merged_at  = ISO now UTC
     state.states.COMPLETION.merge_commit = merge_hash
     state.current_state = "COMPLETED"
     write state.json
```

---

## 7. Output

Ticket mode:

```
✓ STABLE-1234 merged
  PR:     {pr_url}
  Commit: {merge_hash}
  Branch: {branch} (deleted)
  Jira:   {ticket_id} → Complete
```

PR mode — **name what was not done**:

```
✓ PR #456 merged
  PR:     {pr_url}
  Commit: {merge_hash}
  Branch: {branch} (deleted)
  Jira:   {ticket_id} → Complete        (or: no ticket identified, so not updated)
  Record: no workspace, so state.json was not updated
```

On a stop, print the PASS/FAIL precondition table and the detail lines for the first check that
failed. Suggest a concrete next action (e.g. "Run /core-dev:review-jira to apply the review
comments.").

---

## 8. Safety policy

- The squash merge is the only point at which this plugin touches `main`. A stop must be
  conspicuous; a success message should be brief.
- Never bypass branch protection: use `gh pr merge`, never raw `git merge` or
  `git push origin main`.
- Never use `--no-verify` or `--admin` to skip checks.
- Never run `git branch -D` on anything but this ticket's feature branch, and only once
  `git branch --merged` confirms it is fully merged.
- After a partial failure, never re-run `gh pr merge` without first re-checking pr.state with
  `gh pr view` — the merge may in fact have succeeded server-side.
- Every Jira and gh API call is written to `{workspace}/logs/merge.log` so the user can audit
  what ran.
