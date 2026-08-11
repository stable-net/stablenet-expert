---
description: Collect the review comments on a ticket's PR, classify them, and send only what needs changing back through the pipeline.
argument-hint: "<Jira ticket number, e.g. STABLE-1234>"
---

# /core-dev:review-jira

Read PR code-review feedback and carry out the resulting fixes.

---

## 1. Validate the argument + find the ticket's PR

```
1.1. Check the argument shape
   - no match on /^[A-Z]+-\d+$/ -> print usage and stop:
     "usage: /core-dev:review-jira <Jira ticket number>
      e.g.: /core-dev:review-jira STABLE-1234"

1.2. Find this ticket's PR (the same path as merge.md §2.1-2.3)
   Scan {repo_root}/.stablenet-expert/tickets/{jira_id}_* (newest timestamp first).
   Take the first whose state.current_state is in {"COMPLETION","COMPLETED"}.
   workspace = that directory            # every later step uses this
   state     = workspace/state.json
   pr_url    = state.states.COMPLETION.pr_url
   pr_number = /pull/(\d+) from pr_url
   owner/repo = extracted from pr_url (or `gh repo view --json owner,name`)

   With no workspace, or an empty pr_url, stop:
     "No PR found for {jira_id}.
      Create one first with /core-dev:work-with-jira {jira_id}."
```

> This command assumes a **PR this pipeline produced** — the workspace is what gives the review
> results somewhere to go back to. To review an arbitrary PR, use
> `/core-dev:review-pr <PR-URL>`.

---

## 2. Check gh CLI authentication

```
2.1. gh CLI installed and authenticated
   bash: gh auth status 2>&1
   no "Logged in" -> stop:
     "The GitHub CLI needs authentication. Run `gh auth login` and try again."
```

---

## 3. Collect PR information

```
3.1. PR basics
   bash: gh pr view {pr_number} \
     --json number,title,body,headRefName,baseRefName,reviewDecision,state,url

   Keep as pr_info.
   pr_info.state == "MERGED" -> say "This PR is already merged. If new work is needed, use
                                     /core-dev:work-with-jira." + stop
   pr_info.state == "CLOSED" -> say so + stop

3.2. Collect review comments (per-file, inline)
   bash: gh api repos/{owner}/{repo}/pulls/{pr_number}/comments --paginate

   Result: [
     {
       "id": ...,
       "path": "consensus/wbft/finalize.go",
       "line": 89,
       "body": "...",
       "user": { "login": "..." },
       "created_at": "..."
     },
     ...
   ]
   -> keep as inline_comments

3.3. Collect review-level comments
   bash: gh api repos/{owner}/{repo}/pulls/{pr_number}/reviews --paginate

   Result: [
     {
       "id": ...,
       "state": "APPROVED" | "CHANGES_REQUESTED" | "COMMENTED",
       "body": "...",
       "user": { "login": "..." },
       "submitted_at": "..."
     },
     ...
   ]
   -> keep as reviews

3.4. No comments
   When inline_comments and reviews are both empty:
     say: "There are no review comments. Nothing to do."
     stop
```

---

## 4. Classify and structure the review comments

```
4.1. Decide the next review-feedback-{N} number
   bash: ls {workspace}/review-feedback-*.md 2>/dev/null | wc -l
   N = that + 1

4.2. Classify each inline comment
   for each comment in inline_comments:
     classification prompt:
       "Classify this code review comment.
        file: {comment.path}
        line: {comment.line}
        body: {comment.body}

        type (one of):
        - bug_fix: a bug or logic error
        - security: a security vulnerability
        - test_addition: add or improve a test
        - code_quality: style or quality
        - architecture: a structural change
        - question: a question about the code
        - nit: a minor improvement

        severity (one of):
        - critical: must fix (security, serious bug)
        - high: needs fixing (logic error)
        - medium: should fix
        - low: optional

        return: JSON { type, severity, reasoning }"

     -> classified_comments.push({
         original: comment,
         type: ...,
         severity: ...,
         reasoning: ...
       })

4.3. Classify the review-level bodies (reviews[].body)
   Same method. Group by reviewer when there is more than one.

4.4. Write review-feedback-{N}.md
   Template:
   ```markdown
   # Review Feedback #{N}
   PR: {pr_info.url}
   PR Title: {pr_info.title}
   Review Decision: {pr_info.reviewDecision}
   Collected at: {current ISO timestamp}

   ## Reviewers
   - {reviewer}: {state (APPROVED/CHANGES_REQUESTED/COMMENTED)} ({submitted_at})

   ## Inline Comments

   ### File: consensus/wbft/finalize.go
   #### Line 89 [bug_fix / high]
   > "The nil check is missing here. gov_validator can be called before it is initialized."
   - reviewer: {user.login}
   - why this classification: {reasoning}

   #### Line 145 [test_addition / medium]
   > "..."
   ...

   ### File: ...

   ## General Comments
   - [code_quality / low] {reviewer}: "..."
   - [question / low] {reviewer}: "..."
   ```

4.5. Print the classification summary
   - total comments
   - by severity (critical: N, high: N, ...)
   - by type (bug_fix: N, test_addition: N, ...)
```

---

## 5. State transition + Orchestrator dispatch

```
5.1. Record the review cycle in failure_log
   state-machine.log_failure(workspace, {
     state: state.current_state,
     agent: "external_reviewer",
     step: "code_review",
     attempted_action: {
       description: "PR code review cycle",
       related_pr: pr_info.url
     },
     expected_outcome: "PR approved",
     actual_outcome: {
       type: "review_changes_requested",
       summary: "{critical count} critical, {high count} high requested",
       details: "see review-feedback-{N}.md"
     },
     resolution: {
       action: "retry_cycle",
       transitioned_to: "ANALYSIS",
       retry_count: <existing review cycles + 1>
     }
   })

5.2. Force the state to ANALYSIS
   Enter ANALYSIS regardless of the current state:
     state.current_state = "ANALYSIS"
     state.states.ANALYSIS.status = "in_progress"
     state.states.ANALYSIS.started_at = now()
   Write state.json

5.3. Dispatch the Orchestrator
   Agent(
     subagent_type="orchestrator",
     description="Apply review feedback for {jira_id}",
     prompt="
       workspace_dir={workspace}
       mode=review_cycle
       review_feedback_file=review-feedback-{N}.md
       pr_url={pr_info.url}
     "
   )

5.4. On completion, print
   "Started work applying the PR review feedback.
    workspace: {workspace}
    review-feedback-{N}.md: {classified comment count} comment(s)"
```

---

## 6. Done when (checklist)

- [ ] A JIRA-ID not matching the expected form prints usage
- [ ] A clear error when the gh CLI is unauthenticated
- [ ] A ticket with no pipeline workspace, or no recorded pr_url, stops with the reason
- [ ] Review comments classified into the seven types
      (bug_fix/security/test_addition/code_quality/architecture/question/nit)
- [ ] Automatically tagged with one of four severities (critical/high/medium/low)
- [ ] review-feedback-{N}.md structures inline comments per file, separate from general comments
- [ ] Merged and closed PRs are refused
- [ ] No comments -> say so and stop
- [ ] The review cycle is recorded in failure_log
