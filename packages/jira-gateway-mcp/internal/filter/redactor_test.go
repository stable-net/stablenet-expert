package filter

import (
	"testing"

	"github.com/stable-net/stablenet-expert/packages/jira-gateway-mcp/internal/types"
)

var redactConfig = types.PatternsConfig{
	BlockBehavior:     "abort_with_report",
	RedactReplacement: "[REDACTED:{pattern_id}]",
	WarnBehavior:      "pass_with_metadata",
	MaxScanSizeBytes:  1 << 20,
}

func TestRedact_NoMatches(t *testing.T) {
	if got := redact("hello world", nil, redactConfig); got != "hello world" {
		t.Fatalf("got %q; want unchanged", got)
	}
}

func TestRedact_SingleMatch(t *testing.T) {
	text := "DB: postgres://admin:secret@host"
	matches := []types.FilterMatch{
		{PatternID: "db_url", Severity: types.SeverityHigh, Action: types.ActionRedact, Start: 4, End: 32},
	}
	got := redact(text, matches, redactConfig)
	want := "DB: [REDACTED:db_url]"
	if got != want {
		t.Fatalf("got %q; want %q", got, want)
	}
}

func TestRedact_MultipleNonOverlapping(t *testing.T) {
	text := "key1=AAAA token=BBBB end"
	matches := []types.FilterMatch{
		{PatternID: "k1", Severity: types.SeverityHigh, Action: types.ActionRedact, Start: 5, End: 9},
		{PatternID: "k2", Severity: types.SeverityHigh, Action: types.ActionRedact, Start: 16, End: 20},
	}
	got := redact(text, matches, redactConfig)
	want := "key1=[REDACTED:k1] token=[REDACTED:k2] end"
	if got != want {
		t.Fatalf("got %q; want %q", got, want)
	}
}

func TestRedact_PreservesOrderWithArbitraryInput(t *testing.T) {
	text := "AAAA BBBB CCCC"
	matches := []types.FilterMatch{
		{PatternID: "a", Action: types.ActionRedact, Start: 0, End: 4},
		{PatternID: "c", Action: types.ActionRedact, Start: 10, End: 14},
		{PatternID: "b", Action: types.ActionRedact, Start: 5, End: 9},
	}
	got := redact(text, matches, redactConfig)
	want := "[REDACTED:a] [REDACTED:b] [REDACTED:c]"
	if got != want {
		t.Fatalf("got %q; want %q", got, want)
	}
}

func TestRedact_OuterWinsOverInner(t *testing.T) {
	text := "AAAABBBB"
	matches := []types.FilterMatch{
		{PatternID: "outer", Action: types.ActionRedact, Start: 0, End: 8},
		{PatternID: "inner", Action: types.ActionRedact, Start: 2, End: 6},
	}
	got := redact(text, matches, redactConfig)
	want := "[REDACTED:outer]"
	if got != want {
		t.Fatalf("got %q; want %q (outer should win)", got, want)
	}
}
