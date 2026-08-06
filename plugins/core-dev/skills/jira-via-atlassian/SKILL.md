---
name: jira-via-atlassian
description: "How to read and update Jira through the official Atlassian MCP plugin: resolving cloudId once per run, the tool mapping the pipeline uses, and the three-tier transition matching that turns a workflow-independent target like \"Done\" into a transition id. Load this before any Jira call."
type: skill
---

# Jira via the Atlassian MCP

core-dev reads its work item from Jira through the **official Atlassian MCP plugin**
(`mcp__plugin_atlassian_atlassian__*`), not through a server this repository ships
([ADR-0013](../../../../docs/adr/ADR-0013-retire-jira-gateway-adopt-atlassian-mcp.md)).

Two things that used to be handled inside the retired `jira-gateway` server are now the
caller's job, and both are here so that `orchestrator` and `/core-dev:merge` share one
description of them instead of two that drift apart.

## 1. Resolve `cloudId` once per run

Every Atlassian tool takes a `cloudId`. It is not a setting; it identifies which Atlassian
site you are talking to.

```
mcp__plugin_atlassian_atlassian__getAccessibleAtlassianResources()
```

- **One site** → use its id. No question to ask.
- **Several** → ask the user once, with `AskUserQuestion`, and reuse the answer for the rest
  of the run. Do not ask again per call.

Resolve it **before the first Jira call** and carry it. Calling
`getAccessibleAtlassianResources` per operation turns one round trip into many.

If the call fails with an authentication error, the plugin is installed but not
authenticated. Say so and stop — the fix is `claude mcp login plugin:atlassian:atlassian`,
which the user runs in their own terminal (it needs a real terminal; a Bash tool call does
not give it one). `/stablenet-expert:doctor` offers the same thing as part of setup.

## 2. Tool mapping

| What the pipeline needs | Atlassian MCP tool |
|---|---|
| Read a ticket | `getJiraIssue(cloudId, issueIdOrKey, responseContentFormat: "markdown")` |
| Search | `searchJiraIssuesUsingJql(cloudId, jql, maxResults, nextPageToken?)` |
| Comment | `addCommentToJiraIssue(cloudId, issueIdOrKey, commentBody)` |
| List transitions | `getTransitionsForJiraIssue(cloudId, issueIdOrKey)` |
| Apply a transition | `transitionJiraIssue(cloudId, issueIdOrKey, transition: {id})` |
| Reassign | `editJiraIssue(cloudId, issueIdOrKey, fields: {assignee: {accountId}})` |
| Look up a person | `lookupJiraAccountId(cloudId, searchString)` |

**Always pass `responseContentFormat: "markdown"` when reading an issue.** Jira's API returns
ADF (Atlassian Document Format), a nested JSON tree. Asking for markdown makes the server
convert it, which is why `template-parse` can still assume it receives markdown.

## 3. Status transition — three-tier matching

Jira workflows name their transitions differently per project, so `"Done"` may be a
transition name in one project, a target status in another, and only a status *category* in a
third. Ask for the candidates, then match in this order — the first hit wins:

1. **Transition name** — `transition.name` equals the target
2. **Target status name** — `transition.to.name` equals the target
3. **Status category key** — `transition.to.statusCategory.key` equals the target
   (`"done"`, `"indeterminate"`, `"new"`)

All three comparisons are **case-insensitive**, on trimmed strings.

```
transitions = getTransitionsForJiraIssue(cloudId, ticket)
target_l    = target.strip().lower()

for tier in (t.name, t.to.name, t.to.statusCategory.key):
    match = first t in transitions where tier(t).strip().lower() == target_l
    if match: break

if not match:
    # Do not guess a neighbour. Report what the workflow actually offers.
    fail: 'transition "{target}" not available for {ticket}; available: ' +
          ", ".join(f"{t.name} → {t.to.name} ({t.to.statusCategory.key})")

transitionJiraIssue(cloudId, ticket, transition={"id": match.id})
```

**When nothing matches, stop and report the available transitions** — never fall back to
whatever looks closest. A pipeline that silently moves a ticket to the wrong state is worse
than one that stops and says the workflow does not have that step: the first is discovered
days later by a human wondering why their board is wrong.

This is the same three-tier rule `jira-gateway`'s `TransitionIssue` applied, kept so that
existing project workflows keep working across the migration.

## 4. Before posting anything

Comments and PR bodies go through `pr-sanitize` first. The retired server filtered inbound
Jira content on the way in; the official plugin does not
([ADR-0013](../../../../docs/adr/ADR-0013-retire-jira-gateway-adopt-atlassian-mcp.md) §2.3
records that this protection was given up deliberately). Outbound sanitisation is unchanged
and still required.
