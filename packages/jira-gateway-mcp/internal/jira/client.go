package jira

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/stable-net/stablenet-expert/packages/jira-gateway-mcp/internal/types"
)

// ErrAuthFailed is returned when Jira responds with 401.
var ErrAuthFailed = errors.New("jira: authentication failed (check JIRA_API_TOKEN/JIRA_USER_EMAIL)")

// ErrNotFound is returned when Jira responds with 404.
var ErrNotFound = errors.New("jira: resource not found")

// Client is a thin Jira Cloud REST v3 client. It does NOT apply filtering
// or any other policy beyond ADF→Markdown conversion.
type Client struct {
	baseURL    string
	authHeader string
	http       *http.Client
	maxRetries int
	baseDelay  time.Duration
}

// NewClient constructs a client from environment variables.
// Required: JIRA_BASE_URL, JIRA_API_TOKEN, JIRA_USER_EMAIL.
func NewClient() (*Client, error) {
	baseURL := strings.TrimRight(os.Getenv("JIRA_BASE_URL"), "/")
	if baseURL == "" {
		return nil, errors.New("JIRA_BASE_URL env var is required")
	}
	token := os.Getenv("JIRA_API_TOKEN")
	if token == "" {
		return nil, errors.New("JIRA_API_TOKEN env var is required")
	}
	email := os.Getenv("JIRA_USER_EMAIL")
	if email == "" {
		return nil, errors.New("JIRA_USER_EMAIL env var is required")
	}
	creds := base64.StdEncoding.EncodeToString([]byte(email + ":" + token))
	return &Client{
		baseURL:    baseURL,
		authHeader: "Basic " + creds,
		http:       &http.Client{Timeout: 30 * time.Second},
		maxRetries: 3,
		baseDelay:  time.Second,
	}, nil
}

// GetIssue fetches a single issue and returns it with ADF→Markdown.
func (c *Client) GetIssue(ctx context.Context, ticketID string) (*types.JiraIssue, error) {
	path := "/rest/api/3/issue/" + url.PathEscape(ticketID) +
		"?fields=summary,description,issuetype,status,assignee,labels,created,updated"

	var raw issueRaw
	if err := c.request(ctx, "GET", path, nil, &raw); err != nil {
		return nil, err
	}
	return normalizeIssue(raw), nil
}

// GetComments fetches comments for an issue. If since is non-empty, only
// comments with Created >= since are returned.
func (c *Client) GetComments(ctx context.Context, ticketID, since string) ([]types.JiraComment, error) {
	path := "/rest/api/3/issue/" + url.PathEscape(ticketID) + "/comment"

	var resp struct {
		Comments []commentRaw `json:"comments"`
	}
	if err := c.request(ctx, "GET", path, nil, &resp); err != nil {
		return nil, err
	}

	out := make([]types.JiraComment, 0, len(resp.Comments))
	for _, cr := range resp.Comments {
		if since != "" && cr.Created < since {
			continue
		}
		out = append(out, types.JiraComment{
			ID:      cr.ID,
			Author:  authorName(cr.Author),
			Body:    ADFToMarkdown(cr.Body),
			Created: cr.Created,
			Updated: cr.Updated,
		})
	}
	return out, nil
}

// AddComment posts a plain-text comment wrapped in a single ADF paragraph.
func (c *Client) AddComment(ctx context.Context, ticketID, body string) error {
	path := "/rest/api/3/issue/" + url.PathEscape(ticketID) + "/comment"
	payload := map[string]any{
		"body": map[string]any{
			"type":    "doc",
			"version": 1,
			"content": []map[string]any{
				{
					"type":    "paragraph",
					"content": []map[string]any{{"type": "text", "text": body}},
				},
			},
		},
	}
	return c.request(ctx, "POST", path, payload, nil)
}

// GetTransitions returns the workflow transitions available for the issue.
func (c *Client) GetTransitions(ctx context.Context, ticketID string) ([]types.JiraTransition, error) {
	path := "/rest/api/3/issue/" + url.PathEscape(ticketID) + "/transitions"
	var resp struct {
		Transitions []transitionRaw `json:"transitions"`
	}
	if err := c.request(ctx, "GET", path, nil, &resp); err != nil {
		return nil, err
	}
	out := make([]types.JiraTransition, 0, len(resp.Transitions))
	for _, t := range resp.Transitions {
		out = append(out, types.JiraTransition{
			ID:         t.ID,
			Name:       t.Name,
			ToStatus:   t.To.Name,
			ToCategory: t.To.StatusCategory.Key,
		})
	}
	return out, nil
}

// TransitionIssue resolves target (case-insensitively) against transition
// name → status name → statusCategory key, then POSTs the transition. (RI-05)
func (c *Client) TransitionIssue(ctx context.Context, ticketID, target string) error {
	trs, err := c.GetTransitions(ctx, ticketID)
	if err != nil {
		return err
	}
	normalized := strings.ToLower(strings.TrimSpace(target))
	var match *types.JiraTransition
	for i, t := range trs {
		if strings.EqualFold(t.Name, normalized) {
			match = &trs[i]
			break
		}
	}
	if match == nil {
		for i, t := range trs {
			if strings.EqualFold(t.ToStatus, normalized) {
				match = &trs[i]
				break
			}
		}
	}
	if match == nil {
		for i, t := range trs {
			if strings.EqualFold(t.ToCategory, normalized) {
				match = &trs[i]
				break
			}
		}
	}
	if match == nil {
		available := make([]string, 0, len(trs))
		for _, t := range trs {
			available = append(available, fmt.Sprintf("%s → %s (%s)", t.Name, t.ToStatus, t.ToCategory))
		}
		return fmt.Errorf("jira: transition %q not available for %s; available: %s",
			target, ticketID, strings.Join(available, ", "))
	}

	path := "/rest/api/3/issue/" + url.PathEscape(ticketID) + "/transitions"
	payload := map[string]any{"transition": map[string]any{"id": match.ID}}
	return c.request(ctx, "POST", path, payload, nil)
}

// UpdateAssignee sets or clears the assignee field. Pass empty accountID to unassign.
func (c *Client) UpdateAssignee(ctx context.Context, ticketID, accountID string) error {
	path := "/rest/api/3/issue/" + url.PathEscape(ticketID)
	var assignee any
	if accountID == "" {
		assignee = nil
	} else {
		assignee = map[string]any{"accountId": accountID}
	}
	payload := map[string]any{"fields": map[string]any{"assignee": assignee}}
	return c.request(ctx, "PUT", path, payload, nil)
}

// SearchIssues runs a JQL query.
func (c *Client) SearchIssues(ctx context.Context, jql string, maxResults int) ([]types.JiraIssue, error) {
	if maxResults <= 0 {
		maxResults = 50
	}
	q := url.Values{}
	q.Set("jql", jql)
	q.Set("maxResults", fmt.Sprintf("%d", maxResults))
	q.Set("fields", "summary,description,issuetype,status,assignee,labels,created,updated")
	// Atlassian removed the legacy GET /rest/api/3/search endpoint (HTTP 410,
	// CHANGE-2046). The replacement is the bounded /search/jql resource, which
	// takes the same jql/maxResults/fields query params and still returns an
	// "issues" array (plus a nextPageToken we don't page through here).
	path := "/rest/api/3/search/jql?" + q.Encode()
	var resp struct {
		Issues []issueRaw `json:"issues"`
	}
	if err := c.request(ctx, "GET", path, nil, &resp); err != nil {
		return nil, err
	}
	out := make([]types.JiraIssue, 0, len(resp.Issues))
	for _, raw := range resp.Issues {
		out = append(out, *normalizeIssue(raw))
	}
	return out, nil
}

// request performs an authenticated HTTP request with retries on 429 and
// transient errors. out is decoded as JSON if non-nil and the response has
// a JSON content type.
func (c *Client) request(ctx context.Context, method, path string, body any, out any) error {
	url := c.baseURL + path
	var lastErr error

	for attempt := 0; attempt < c.maxRetries; attempt++ {
		var reqBody io.Reader
		if body != nil {
			b, err := json.Marshal(body)
			if err != nil {
				return fmt.Errorf("marshal request body: %w", err)
			}
			reqBody = bytes.NewReader(b)
		}
		req, err := http.NewRequestWithContext(ctx, method, url, reqBody)
		if err != nil {
			return err
		}
		req.Header.Set("Authorization", c.authHeader)
		req.Header.Set("Accept", "application/json")
		req.Header.Set("Content-Type", "application/json")

		resp, err := c.http.Do(req)
		if err != nil {
			lastErr = err
			c.sleepBackoff(ctx, attempt)
			continue
		}

		switch resp.StatusCode {
		case http.StatusUnauthorized:
			resp.Body.Close()
			return ErrAuthFailed
		case http.StatusNotFound:
			resp.Body.Close()
			return ErrNotFound
		case http.StatusTooManyRequests:
			resp.Body.Close()
			c.sleepBackoff(ctx, attempt)
			continue
		}

		if resp.StatusCode >= 400 {
			snippet, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
			resp.Body.Close()
			return fmt.Errorf("jira %s %s: status %d: %s",
				method, path, resp.StatusCode, string(snippet))
		}

		if resp.StatusCode == http.StatusNoContent || out == nil {
			resp.Body.Close()
			return nil
		}
		if ct := resp.Header.Get("Content-Type"); !strings.Contains(ct, "application/json") {
			resp.Body.Close()
			return nil
		}
		err = json.NewDecoder(resp.Body).Decode(out)
		resp.Body.Close()
		return err
	}

	if lastErr == nil {
		lastErr = errors.New("jira: max retries exceeded")
	}
	return lastErr
}

func (c *Client) sleepBackoff(ctx context.Context, attempt int) {
	d := c.baseDelay << attempt
	select {
	case <-time.After(d):
	case <-ctx.Done():
	}
}

// --- raw response types (only fields we need) ---

type issueRaw struct {
	Key    string `json:"key"`
	Fields struct {
		Summary     string   `json:"summary"`
		Description any      `json:"description"`
		IssueType   *struct{ Name string } `json:"issuetype"`
		Status      *struct {
			Name           string  `json:"name"`
			StatusCategory *struct{ Key string } `json:"statusCategory"`
		} `json:"status"`
		Assignee *struct{ DisplayName string } `json:"assignee"`
		Labels   []string `json:"labels"`
		Created  string   `json:"created"`
		Updated  string   `json:"updated"`
	} `json:"fields"`
}

type commentRaw struct {
	ID      string `json:"id"`
	Author  *struct{ DisplayName string } `json:"author"`
	Body    any    `json:"body"`
	Created string `json:"created"`
	Updated string `json:"updated"`
}

type transitionRaw struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	To   struct {
		Name           string `json:"name"`
		StatusCategory struct{ Key string } `json:"statusCategory"`
	} `json:"to"`
}

func normalizeIssue(r issueRaw) *types.JiraIssue {
	t := "Unknown"
	if r.Fields.IssueType != nil {
		t = r.Fields.IssueType.Name
	}
	status := "Unknown"
	statusCat := "unknown"
	if r.Fields.Status != nil {
		status = r.Fields.Status.Name
		if r.Fields.Status.StatusCategory != nil {
			statusCat = r.Fields.Status.StatusCategory.Key
		}
	}
	assignee := ""
	if r.Fields.Assignee != nil {
		assignee = r.Fields.Assignee.DisplayName
	}
	labels := r.Fields.Labels
	if labels == nil {
		labels = []string{}
	}
	return &types.JiraIssue{
		TicketID:       r.Key,
		Type:           t,
		Summary:        r.Fields.Summary,
		Description:    ADFToMarkdown(r.Fields.Description),
		Assignee:       assignee,
		Status:         status,
		StatusCategory: statusCat,
		Labels:         labels,
		Created:        r.Fields.Created,
		Updated:        r.Fields.Updated,
	}
}

func authorName(a *struct{ DisplayName string }) string {
	if a == nil {
		return "Unknown"
	}
	return a.DisplayName
}
