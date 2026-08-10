---
description: Review a PR in an isolated clone — invariants, side effects, vulnerabilities — then write up the verdict and either approve or comment.
argument-hint: "<PR URL or #number, e.g. https://github.com/org/repo/pull/456>"
allowed-tools: Read, Write, Edit, Bash, Agent, Skill, TodoWrite, AskUserQuestion, mcp__plugin_core-dev_stablenet-knowledge, mcp__plugin_atlassian_atlassian
---

# /core-dev:review-pr

Read and review any PR. Unlike `review-jira`, the PR need not have come from this pipeline, and
no workspace is involved.

> **This command comments on a PR and can approve it** — outward-facing actions that are hard to
> take back. Do not skip the confirmation in §7.

---

## 1. Validate the argument

```
1.1. PR URL or #number
     "https://github.com/<owner>/<repo>/pull/<n>" -> owner, repo, pr_number
     "#<n>" or "<n>" -> resolve against the current repo: bash: gh repo view --json owner,name
     anything else -> print usage and stop:
       "usage: /core-dev:review-pr <PR URL or #number>"

1.2. bash: gh auth status   stop on failure (point at `gh auth login`)

1.3. bash: gh pr view {pr_number} --repo {owner}/{repo} \
       --json number,title,body,headRefName,baseRefName,state,url,headRepository,isCrossRepository
     state MERGED/CLOSED -> say so and stop. There is nothing to review.
```

---

## 2. Clone in isolation

Review happens **outside the checkout being worked in**. Switching branches or touching the stash
wrecks whatever the user had in progress, and code under review mixed with local changes makes it
impossible to tell what is actually being read.

```
2.1. Target path -- carries the PR number so concurrent reviews cannot overwrite each other
     workdir = /tmp/core-dev-review-pr{pr_number}-{owner}-{repo}

2.2. Remove any existing one and fetch fresh. Reading on top of a previous review's leftovers
     is not reading this PR.
     bash: rm -rf {workdir}

2.3. bash: gh repo clone {owner}/{repo} {workdir} -- --quiet
     (Clone the base repo even for a PR from a fork -- `gh pr checkout` wires up the fork
      remote itself.)

2.4. bash: cd {workdir} && gh pr checkout {pr_number}
     Stop on failure and report gh's output verbatim.

2.5. Every later command runs as `git -C {workdir}` or `cd {workdir} && ...`.
     Do no review work in the user's own directory.
```

---

## 3. Establish what changed

```
3.1. base = pr_info.baseRefName
     bash: git -C {workdir} fetch -q origin {base}
     bash: git -C {workdir} merge-base HEAD origin/{base}   -> merge_base

3.2. bash: git -C {workdir} diff --stat {merge_base}...HEAD
     bash: git -C {workdir} diff {merge_base}...HEAD
     bash: git -C {workdir} log --oneline {merge_base}..HEAD

     Use `...`. With `..` the diff folds in whatever happened on base meanwhile, which puts
     changes this PR never made in front of the review.

3.3. Build the changed-file list, distinguishing added, deleted and renamed.
     If the diff is empty, report that and stop.
```

---

## 4. Review — three axes

Each axis draws its **evidence** from `stablenet-knowledge`. A finding with no evidence behind it
gets dropped in §6.

```
4.1. Implementation constraints -- are there rules this code has to hold to
     mcp: cks_context_find_invariants(changed modules/symbols)
     mcp: cks_context_get_conventions(changed paths)
     mcp: cks_context_get_invariant_enforcement(relevant invariants)

     A change that breaks an invariant is a defect even when nothing misbehaves yet, and there
     is something concrete to cite for it.

4.2. Side effects -- how far does this reach through the graph
     For each changed function/type:
       mcp: cks_context_find_callers(symbol)       do callers rely on an assumption this breaks
       mcp: cks_context_impact_analysis(symbol)    how far the change propagates
       mcp: cks_context_concurrency_impact(symbol) are there locking or ordering assumptions

     An unchanged signature whose **meaning** changed still breaks callers. What surfaces here
     is the conditions on a return value, whether nil is allowed, required call order.

4.3. Vulnerabilities -- what can an attacker do with this change
     Fix the trust boundary first: of the inputs reaching this code, which come from outside.
       - input flowing through unvalidated (paths, commands, queries, deserialization)
       - a newly opened path around an authorization check
       - integer overflow/underflow and boundary arithmetic (especially consensus/quorum code)
       - secrets, keys or tokens landing in the diff
       - denial of service: unbounded loops, unbounded allocation, externally driven retries

     "This looks unsafe" is not a finding. Write **who supplies what, and what it becomes.**
```

Collect each finding into `{workdir}/review-findings.json` in this shape:

```json
{"id": "f1", "file": "consensus/wbft/core.go", "line": 214,
 "severity": "critical|major|minor",
 "axis": "invariant|side-effect|security",
 "claim": "what is wrong and why -- by a concrete path",
 "evidence": "a cks tool result or a code citation",
 "suggestion": "how to fix it (optional)"}
```

---

## 5. Write the verdict

```
5.1. Write {workdir}/review-report.md
     - PR number, title, base, commit count, size of the change
     - what was examined and what was found, per axis (write "none" when nothing was found --
       an empty section is indistinguishable from an axis nobody looked at)
     - what could not be checked: modules absent from the index, tests that were not run.
       Without the limits written down, a reader takes the review for exhaustive.
5.2. Tell the user the path. This document is not posted to the PR.
```

---

## 6. Second opinion — a different model

```
6.1. Launch `review-adjudicator` with the Agent tool (a different model).
     Send: findings.json path, workdir, merge_base
     Receive: keep/drop per finding with a reason (+ wording corrections)

6.2. Dropped findings are **discarded.** Do not revive them.
     This stage exists to stop unnecessary change requests and findings built on a misreading,
     not to ask once more and keep the original conclusion.

6.3. Where a correction is attached, adopt that wording.

6.4. If the adjudicator fails or comes back empty, **post nothing.**
     Posting an unreviewed review is worse than posting none. Keep the report and say so.
```

---

## 7. Post — after confirmation

```
7.1. Clear pr-sanitize
     For every remaining claim/suggestion:
       result = pr-sanitize.scan(text=..., context="pr_review_comment")
     BLOCKED -> post nothing, stop, report what tripped it.

7.2. Confirm with the user -- AskUserQuestion
     With findings:
       header: "Post review"
       question: "This posts {n} comment(s) on {owner}/{repo}#{pr_number}.
                  critical {a} / major {b} / minor {c}. Summary: ...
                  Posting is visible to others and sends notifications."
       options:
         - "Post it"
         - "Don't post (report only)"
     With none:
       header: "Approve PR"
       question: "Nothing to raise. Approve {owner}/{repo}#{pr_number} with LGTM?
                  An approval is visible to others."
       options:
         - "Approve it"
         - "Don't approve (report only)"

     Never post or approve without confirmation. Approving on its own is not this command's job.

7.3. No findings, approval chosen
     bash: cd {workdir} && gh pr review {pr_number} --approve \
             --body "LGTM -- {one-line summary}. Reviewed: invariants / side effects / security."

7.4. Findings, posting chosen
     Post the comments:
       bash: cd {workdir} && gh pr review {pr_number} --comment \
               --body "{combined comment}"
     Give each finding its file and line in the body.
     **Do not use --request-changes.** Leave room for a human to judge; this command is not a
     blocker.

7.5. Give the report path even when nothing is posted.
```

---

## 8. Clean up

```
8.1. Leave {workdir} in place. The report is inside it and the user has to be able to read it.
     Print the path and say to remove it when done:
       rm -rf {workdir}
8.2. The user's own directory must be exactly as this command found it.
     Confirm no branch, stash or index was touched.
```

---

## 9. Done when (checklist)

- [ ] Cloned under `/tmp`, at a path carrying the PR number
- [ ] PR code checked out with `gh pr checkout`
- [ ] Diffed with `{merge_base}...HEAD` (not `..`)
- [ ] All three axes reviewed with stablenet-knowledge evidence
- [ ] `review-report.md` written, limits stated
- [ ] Second opinion from the adjudicator on a different model; drops discarded
- [ ] User confirmed before posting or approving
- [ ] pr-sanitize cleared
- [ ] User's original checkout untouched
