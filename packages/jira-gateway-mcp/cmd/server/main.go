// Command server runs the Jira Gateway MCP server over stdio.
//
// Required environment variables:
//
//	JIRA_BASE_URL    Jira Cloud base URL (no trailing slash)
//	JIRA_API_TOKEN   API token from id.atlassian.com
//	JIRA_USER_EMAIL  Email associated with the token
//
// Optional:
//
//	PATTERNS_PATH         path to packages/shared-patterns/patterns.json (auto-detected otherwise)
//	CUSTOM_PATTERNS_PATH  path to override pattern file
package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/0xmhha/stablenet-expert/packages/jira-gateway-mcp/internal/jira"
	srv "github.com/0xmhha/stablenet-expert/packages/jira-gateway-mcp/internal/server"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "[jira-gateway-mcp] fatal: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
	jiraClient, err := jira.NewClient()
	if err != nil {
		return fmt.Errorf("init jira client: %w", err)
	}

	server := mcp.NewServer(&mcp.Implementation{
		Name:    "jira-gateway",
		Version: "0.1.0",
	}, nil)

	srv.Register(server, srv.Deps{Jira: jiraClient})

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	transport := &mcp.StdioTransport{}
	return server.Run(ctx, transport)
}
