// Package types defines the data structures shared across the jira-gateway-mcp.
package types

// Severity levels used by filter patterns.
type Severity string

const (
	SeverityCritical Severity = "critical"
	SeverityHigh     Severity = "high"
	SeverityMedium   Severity = "medium"
	SeverityWarning  Severity = "warning"
)

// FilterAction is what the engine does with a matched range.
type FilterAction string

const (
	ActionBlock  FilterAction = "block"
	ActionRedact FilterAction = "redact"
	ActionWarn   FilterAction = "warn"
)

// ScanResult is the aggregate outcome of a filter scan.
type ScanResult string

const (
	ScanClean       ScanResult = "CLEAN"
	ScanRedacted    ScanResult = "REDACTED"
	ScanBlocked     ScanResult = "BLOCKED"
	ScanLocalBypass ScanResult = "LOCAL_BYPASS"
)

// Pattern is the on-disk representation of a single filter rule. Either a
// regex or an entropy-based detector. Validation is centralized in patterns.go.
type Pattern struct {
	ID              string       `json:"id"`
	Name            string       `json:"name"`
	Regex           string       `json:"regex,omitempty"`
	Type            string       `json:"type,omitempty"`
	Threshold       float64      `json:"threshold,omitempty"`
	MinLength       int          `json:"min_length,omitempty"`
	MaxLength       int          `json:"max_length,omitempty"`
	Severity        Severity     `json:"severity"`
	Action          FilterAction `json:"action"`
	ExcludePatterns []string     `json:"exclude_patterns,omitempty"`
	Description     string       `json:"description,omitempty"`
}

// IsEntropy reports whether the pattern is an entropy-based detector.
func (p Pattern) IsEntropy() bool { return p.Type == "entropy" }

// PatternsConfig is the top-level config block in patterns.json.
type PatternsConfig struct {
	BlockBehavior     string `json:"block_behavior"`
	RedactReplacement string `json:"redact_replacement"`
	WarnBehavior      string `json:"warn_behavior"`
	MaxScanSizeBytes  int    `json:"max_scan_size_bytes"`
}

// PatternsFile is the root JSON document loaded from shared/patterns.json.
type PatternsFile struct {
	Version  string         `json:"version"`
	Patterns []Pattern      `json:"patterns"`
	Config   PatternsConfig `json:"config"`
}

// FilterMatch describes a matched range within a scanned text.
type FilterMatch struct {
	PatternID string
	Severity  Severity
	Action    FilterAction
	Start     int
	End       int
}

// FilterMetadata is exposed to callers so the agent can branch on scan_result.
// Never include the matched secret values here.
type FilterMetadata struct {
	ScanResult       ScanResult `json:"scan_result"`
	RedactedCount    int        `json:"redacted_count"`
	RedactedPatterns []string   `json:"redacted_patterns"`
	BlockedPatterns  []string   `json:"blocked_patterns"`
	Warnings         []string   `json:"warnings"`
	ScannedAt        string     `json:"scanned_at"`
}

// FilterResult is the engine's return value: sanitized text + metadata.
type FilterResult struct {
	Text     string
	Metadata FilterMetadata
}

// JiraIssue is the normalized representation of a Jira issue returned by
// the gateway. Description is ADF-converted Markdown.
type JiraIssue struct {
	TicketID       string   `json:"ticket_id"`
	Type           string   `json:"type"`
	Summary        string   `json:"summary"`
	Description    string   `json:"description"`
	Assignee       string   `json:"assignee,omitempty"`
	Status         string   `json:"status"`
	StatusCategory string   `json:"status_category"`
	Labels         []string `json:"labels"`
	Created        string   `json:"created"`
	Updated        string   `json:"updated"`
}

// JiraComment is the normalized representation of a Jira comment.
type JiraComment struct {
	ID      string `json:"id"`
	Author  string `json:"author"`
	Body    string `json:"body"`
	Created string `json:"created"`
	Updated string `json:"updated"`
}

// JiraTransition is a workflow transition available for an issue (RI-05).
type JiraTransition struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	ToStatus   string `json:"to_status"`
	ToCategory string `json:"to_category"`
}
