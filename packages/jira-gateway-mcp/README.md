# jira-gateway-mcp

Jira Gateway MCP server (Go) with sensitive information filtering for the
`core-dev` plugin (part of the `stablenet-expert` marketplace).

This server is a thin proxy between the LLM agent and Jira Cloud REST API v3.
It applies pattern-based and entropy-based sensitive information filtering on
read responses **before** they reach the LLM context.

## Architecture

```
Agent (LLM) → jira-gateway MCP → Jira Cloud REST API v3
                  ↓
       Sensitive Filter (BLOCK / REDACT / WARN)
```

- **Read tools** (`jira_read_ticket`, `jira_read_comments`, `jira_search`) —
  responses are filtered. Each response includes `_filter_metadata.scan_result`
  with one of `CLEAN` / `REDACTED` / `BLOCKED`.
- **Write tools** (`jira_add_comment`, `jira_update_status`,
  `jira_update_assignee`) — passthrough; not filtered.

## Design notes

### ADF handling (RI-04)

Jira Cloud API v3 returns description and comment bodies in
Atlassian Document Format (ADF). The client converts ADF → Markdown in
`internal/jira/adf.go` so downstream callers always see Markdown.

### Transition handling (RI-05)

`jira_update_status` accepts a transition name, target status name, or
status category key (e.g. `"In Review"`, `"Done"`, `"done"`). The client
looks up available transitions via the Jira API and matches case-insensitively
so workflows with custom transition names continue to work.

### Fail-safe (RI-06)

If the filter engine fails for any reason (missing patterns file, malformed
regex, oversized payload, …) the engine returns `BLOCKED` with an empty
`text` field. The original text is never returned on filter failure.

## Layout

```
packages/jira-gateway-mcp/
├── cmd/server/main.go        # stdio MCP server entrypoint
├── internal/
│   ├── filter/               # sensitive filter engine
│   ├── jira/                 # Jira REST client + ADF→Markdown
│   ├── server/               # MCP tool registration + handlers
│   └── types/                # shared types
├── go.mod
└── README.md
```

## Build

```bash
go build -o bin/jira-gateway-mcp ./cmd/server
```

## Test

```bash
go test ./...
```

## Run (manual)

```bash
export JIRA_BASE_URL=https://your-domain.atlassian.net
export JIRA_API_TOKEN=...
export JIRA_USER_EMAIL=...
./bin/jira-gateway-mcp
```

The server speaks the MCP protocol over stdio; it is intended to be launched
by Claude Code via the plugin's `.mcp.json` registration rather than
run interactively.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `JIRA_BASE_URL` | ✓ | Jira Cloud base URL (no trailing slash) |
| `JIRA_API_TOKEN` | ✓ | Jira API token |
| `JIRA_USER_EMAIL` | ✓ | Email associated with the token |
| `PATTERNS_PATH` | | Path to `packages/sensitive-guard/patterns.json` (auto-detected otherwise) |
| `CUSTOM_PATTERNS_PATH` | | Path to override pattern file |
