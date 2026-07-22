// Package server wires Jira Gateway MCP tools onto an mcp.Server.
package server

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/stable-net/stablenet-expert/packages/jira-gateway-mcp/internal/filter"
	"github.com/stable-net/stablenet-expert/packages/jira-gateway-mcp/internal/jira"
	"github.com/stable-net/stablenet-expert/packages/jira-gateway-mcp/internal/types"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// Deps is the injection point so tests can swap the Jira client.
type Deps struct {
	Jira *jira.Client
}

// Register attaches all 6 Jira Gateway tools to the given server.
//
// Read tools (filter applied):
//   - jira_read_ticket
//   - jira_read_comments
//   - jira_search
//
// Write tools (passthrough):
//   - jira_add_comment
//   - jira_update_status
//   - jira_update_assignee
func Register(s *mcp.Server, deps Deps) {
	mcp.AddTool(s, &mcp.Tool{
		Name: "jira_read_ticket",
		Description: "Read a Jira ticket by ID. Description and summary are filtered " +
			"for sensitive information before returning. Includes _filter_metadata " +
			"with scan_result (CLEAN/REDACTED/BLOCKED).",
	}, makeReadTicketHandler(deps))

	mcp.AddTool(s, &mcp.Tool{
		Name: "jira_read_comments",
		Description: "Read comments on a Jira ticket. Comment bodies are filtered " +
			"for sensitive information. Optional 'since' ISO datetime to fetch only newer comments.",
	}, makeReadCommentsHandler(deps))

	mcp.AddTool(s, &mcp.Tool{
		Name: "jira_search",
		Description: "Search Jira issues by JQL. Each result's summary and description are filtered.",
	}, makeSearchHandler(deps))

	mcp.AddTool(s, &mcp.Tool{
		Name: "jira_add_comment",
		Description: "Add a comment to a Jira ticket. Body is sent as-is (passthrough).",
	}, makeAddCommentHandler(deps))

	mcp.AddTool(s, &mcp.Tool{
		Name: "jira_update_status",
		Description: "Transition a Jira ticket. Accepts transition name, target status name, " +
			"or statusCategory key (case-insensitive lookup, RI-05).",
	}, makeUpdateStatusHandler(deps))

	mcp.AddTool(s, &mcp.Tool{
		Name: "jira_update_assignee",
		Description: "Update the assignee of a Jira ticket. Empty account_id unassigns.",
	}, makeUpdateAssigneeHandler(deps))
}

// --- Inputs ---

type readTicketInput struct {
	TicketID string `json:"ticket_id" jsonschema:"Jira ticket ID, e.g. STABLE-1234"`
}
type readCommentsInput struct {
	TicketID string `json:"ticket_id"`
	Since    string `json:"since,omitempty" jsonschema:"ISO 8601 datetime; only newer comments returned"`
}
type searchInput struct {
	JQL        string `json:"jql"`
	MaxResults int    `json:"max_results,omitempty"`
}
type addCommentInput struct {
	TicketID string `json:"ticket_id"`
	Body     string `json:"body"`
}
type updateStatusInput struct {
	TicketID string `json:"ticket_id"`
	Target   string `json:"target" jsonschema:"Transition name, status name, or statusCategory key"`
}
type updateAssigneeInput struct {
	TicketID  string `json:"ticket_id"`
	AccountID string `json:"account_id,omitempty"`
}

// --- Output payloads ---

type readTicketOutput struct {
	TicketID       string               `json:"ticket_id"`
	Type           string               `json:"type"`
	Summary        string               `json:"summary"`
	Description    string               `json:"description"`
	Assignee       string               `json:"assignee,omitempty"`
	Status         string               `json:"status"`
	StatusCategory string               `json:"status_category"`
	Labels         []string             `json:"labels"`
	Created        string               `json:"created"`
	Updated        string               `json:"updated"`
	FilterMetadata types.FilterMetadata `json:"_filter_metadata"`
}

type readCommentsOutput struct {
	TicketID       string               `json:"ticket_id"`
	Comments       []types.JiraComment  `json:"comments"`
	FilterMetadata types.FilterMetadata `json:"_filter_metadata"`
}

type searchOutput struct {
	Results        []types.JiraIssue    `json:"results"`
	FilterMetadata types.FilterMetadata `json:"_filter_metadata"`
}

type okOutput struct {
	OK       bool   `json:"ok"`
	TicketID string `json:"ticket_id"`
	Detail   string `json:"detail,omitempty"`
}

// --- Handlers ---

func makeReadTicketHandler(deps Deps) mcp.ToolHandlerFor[readTicketInput, readTicketOutput] {
	return func(ctx context.Context, _ *mcp.CallToolRequest, in readTicketInput) (*mcp.CallToolResult, readTicketOutput, error) {
		if in.TicketID == "" {
			return errResult("INVALID_ARG", "ticket_id is required"), readTicketOutput{}, nil
		}
		raw, err := deps.Jira.GetIssue(ctx, in.TicketID)
		if err != nil {
			return jiraErrResult(err), readTicketOutput{}, nil
		}

		summaryFiltered := filter.ScanAndFilter(raw.Summary)
		descFiltered := filter.ScanAndFilter(raw.Description)
		merged := filter.MergeMetadata(summaryFiltered.Metadata, descFiltered.Metadata)

		if merged.ScanResult == types.ScanBlocked {
			return blockedResult(in.TicketID, merged.BlockedPatterns), readTicketOutput{}, nil
		}

		out := readTicketOutput{
			TicketID:       raw.TicketID,
			Type:           raw.Type,
			Summary:        summaryFiltered.Text,
			Description:    descFiltered.Text,
			Assignee:       raw.Assignee,
			Status:         raw.Status,
			StatusCategory: raw.StatusCategory,
			Labels:         raw.Labels,
			Created:        raw.Created,
			Updated:        raw.Updated,
			FilterMetadata: merged,
		}
		return nil, out, nil
	}
}

func makeReadCommentsHandler(deps Deps) mcp.ToolHandlerFor[readCommentsInput, readCommentsOutput] {
	return func(ctx context.Context, _ *mcp.CallToolRequest, in readCommentsInput) (*mcp.CallToolResult, readCommentsOutput, error) {
		if in.TicketID == "" {
			return errResult("INVALID_ARG", "ticket_id is required"), readCommentsOutput{}, nil
		}
		comments, err := deps.Jira.GetComments(ctx, in.TicketID, in.Since)
		if err != nil {
			return jiraErrResult(err), readCommentsOutput{}, nil
		}

		filteredComments := make([]types.JiraComment, 0, len(comments))
		metas := make([]types.FilterMetadata, 0, len(comments))
		for _, c := range comments {
			fr := filter.ScanAndFilter(c.Body)
			metas = append(metas, fr.Metadata)
			if fr.Metadata.ScanResult == types.ScanBlocked {
				continue // drop the blocked comment; the merged metadata still reflects it
			}
			c.Body = fr.Text
			filteredComments = append(filteredComments, c)
		}

		out := readCommentsOutput{
			TicketID:       in.TicketID,
			Comments:       filteredComments,
			FilterMetadata: filter.MergeMetadata(metas...),
		}
		return nil, out, nil
	}
}

func makeSearchHandler(deps Deps) mcp.ToolHandlerFor[searchInput, searchOutput] {
	return func(ctx context.Context, _ *mcp.CallToolRequest, in searchInput) (*mcp.CallToolResult, searchOutput, error) {
		if in.JQL == "" {
			return errResult("INVALID_ARG", "jql is required"), searchOutput{}, nil
		}
		issues, err := deps.Jira.SearchIssues(ctx, in.JQL, in.MaxResults)
		if err != nil {
			return jiraErrResult(err), searchOutput{}, nil
		}

		filteredResults := make([]types.JiraIssue, 0, len(issues))
		metas := make([]types.FilterMetadata, 0, len(issues)*2)
		for _, issue := range issues {
			sf := filter.ScanAndFilter(issue.Summary)
			df := filter.ScanAndFilter(issue.Description)
			merged := filter.MergeMetadata(sf.Metadata, df.Metadata)
			metas = append(metas, merged)
			if merged.ScanResult == types.ScanBlocked {
				continue
			}
			issue.Summary = sf.Text
			issue.Description = df.Text
			filteredResults = append(filteredResults, issue)
		}

		out := searchOutput{
			Results:        filteredResults,
			FilterMetadata: filter.MergeMetadata(metas...),
		}
		return nil, out, nil
	}
}

func makeAddCommentHandler(deps Deps) mcp.ToolHandlerFor[addCommentInput, okOutput] {
	return func(ctx context.Context, _ *mcp.CallToolRequest, in addCommentInput) (*mcp.CallToolResult, okOutput, error) {
		if in.TicketID == "" || in.Body == "" {
			return errResult("INVALID_ARG", "ticket_id and body are required"), okOutput{}, nil
		}
		if err := deps.Jira.AddComment(ctx, in.TicketID, in.Body); err != nil {
			return jiraErrResult(err), okOutput{}, nil
		}
		return nil, okOutput{OK: true, TicketID: in.TicketID}, nil
	}
}

func makeUpdateStatusHandler(deps Deps) mcp.ToolHandlerFor[updateStatusInput, okOutput] {
	return func(ctx context.Context, _ *mcp.CallToolRequest, in updateStatusInput) (*mcp.CallToolResult, okOutput, error) {
		if in.TicketID == "" || in.Target == "" {
			return errResult("INVALID_ARG", "ticket_id and target are required"), okOutput{}, nil
		}
		if err := deps.Jira.TransitionIssue(ctx, in.TicketID, in.Target); err != nil {
			return jiraErrResult(err), okOutput{}, nil
		}
		return nil, okOutput{OK: true, TicketID: in.TicketID, Detail: "transitioned: " + in.Target}, nil
	}
}

func makeUpdateAssigneeHandler(deps Deps) mcp.ToolHandlerFor[updateAssigneeInput, okOutput] {
	return func(ctx context.Context, _ *mcp.CallToolRequest, in updateAssigneeInput) (*mcp.CallToolResult, okOutput, error) {
		if in.TicketID == "" {
			return errResult("INVALID_ARG", "ticket_id is required"), okOutput{}, nil
		}
		if err := deps.Jira.UpdateAssignee(ctx, in.TicketID, in.AccountID); err != nil {
			return jiraErrResult(err), okOutput{}, nil
		}
		detail := "assignee: " + in.AccountID
		if in.AccountID == "" {
			detail = "assignee cleared"
		}
		return nil, okOutput{OK: true, TicketID: in.TicketID, Detail: detail}, nil
	}
}

// --- Helpers ---

func errResult(code, message string) *mcp.CallToolResult {
	payload := map[string]any{
		"error":       code,
		"message":     message,
		"recoverable": code != "AUTH_FAILED",
	}
	return wrapError(payload)
}

func jiraErrResult(err error) *mcp.CallToolResult {
	switch {
	case errors.Is(err, jira.ErrAuthFailed):
		return errResult("AUTH_FAILED", err.Error())
	case errors.Is(err, jira.ErrNotFound):
		return errResult("NOT_FOUND", err.Error())
	default:
		return errResult("INTERNAL_ERROR", fmt.Sprintf("%v", err))
	}
}

func blockedResult(ticketID string, patterns []string) *mcp.CallToolResult {
	payload := map[string]any{
		"error":             "SENSITIVE_CONTENT_BLOCKED",
		"message":           fmt.Sprintf("Jira ticket %s contains sensitive content that cannot be processed.", ticketID),
		"detected_patterns": patterns,
		"recommendation":    "Remove the sensitive information from the Jira ticket and retry.",
		"recoverable":       false,
	}
	return wrapError(payload)
}

func wrapError(payload map[string]any) *mcp.CallToolResult {
	b, err := json.Marshal(payload)
	if err != nil {
		b = []byte(`{"error":"INTERNAL_ERROR","message":"failed to marshal error payload"}`)
	}
	return &mcp.CallToolResult{
		IsError: true,
		Content: []mcp.Content{&mcp.TextContent{Text: string(b)}},
	}
}
