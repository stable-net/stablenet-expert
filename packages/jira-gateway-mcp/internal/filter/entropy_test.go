package filter

import (
	"testing"

	"github.com/stable-net/stablenet-expert/packages/jira-gateway-mcp/internal/types"
)

var highEntropyPattern = types.Pattern{
	ID:        "high_entropy_string",
	Name:      "High Entropy",
	Type:      "entropy",
	Threshold: 4.5,
	MinLength: 20,
	MaxLength: 200,
	Severity:  types.SeverityWarning,
	Action:    types.ActionWarn,
	ExcludePatterns: []string{
		`^[a-f0-9]+$`,
		`^[A-Z_]+$`,
		`^(https?|ftp)://`,
	},
}

func TestShannonEntropy(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want func(float64) bool
	}{
		{"empty", "", func(f float64) bool { return f == 0 }},
		{"repeated", "aaaaaaaa", func(f float64) bool { return f == 0 }},
		{"varied", "abcdefgh", func(f float64) bool { return f > 2 }},
		{"random high", "aB3$kL9#mN2&pQ5xR8wT4", func(f float64) bool { return f > 4.0 }},
		{"low entropy padded", string(make([]byte, 20)), func(f float64) bool { return f < 1.0 }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := shannonEntropy(tc.in)
			if !tc.want(got) {
				t.Fatalf("entropy(%q) = %v; condition failed", tc.in, got)
			}
		})
	}
}

func TestScanEntropy_DetectsHighEntropyToken(t *testing.T) {
	text := "config: aB3$kL9#mN2&pQ5xR8wT4yU7zV1 token"
	matches := scanEntropy(text, highEntropyPattern)
	if len(matches) == 0 {
		t.Fatalf("expected at least one match, got 0")
	}
	if matches[0].PatternID != "high_entropy_string" {
		t.Fatalf("expected pattern_id 'high_entropy_string', got %q", matches[0].PatternID)
	}
}

func TestScanEntropy_SkipsBelowMinLength(t *testing.T) {
	matches := scanEntropy("aB3kL", highEntropyPattern)
	if len(matches) != 0 {
		t.Fatalf("expected 0 matches for short token, got %d", len(matches))
	}
}

func TestScanEntropy_SkipsAboveMaxLength(t *testing.T) {
	long := make([]byte, 250)
	for i := range long {
		long[i] = byte('a' + (i % 26))
	}
	matches := scanEntropy(string(long), highEntropyPattern)
	if len(matches) != 0 {
		t.Fatalf("expected 0 matches for over-long token, got %d", len(matches))
	}
}

func TestScanEntropy_ExcludesHexHash(t *testing.T) {
	matches := scanEntropy("0123456789abcdef0123456789abcdef", highEntropyPattern)
	if len(matches) != 0 {
		t.Fatalf("expected 0 matches for hex hash (excluded), got %d", len(matches))
	}
}

func TestScanEntropy_ExcludesURL(t *testing.T) {
	matches := scanEntropy("https://example.com/very/long/path/segment", highEntropyPattern)
	if len(matches) != 0 {
		t.Fatalf("expected 0 matches for URL (excluded), got %d", len(matches))
	}
}

func TestScanEntropy_ExcludesAllCapsConstant(t *testing.T) {
	matches := scanEntropy("VERY_LONG_CONSTANT_NAME_HERE", highEntropyPattern)
	if len(matches) != 0 {
		t.Fatalf("expected 0 matches for ALL_CAPS constant (excluded), got %d", len(matches))
	}
}

func TestScanEntropy_CorrectPositions(t *testing.T) {
	text := "prefix aB3$kL9#mN2&pQ5xR8wT4yU7zV1 suffix"
	matches := scanEntropy(text, highEntropyPattern)
	if len(matches) != 1 {
		t.Fatalf("expected exactly 1 match, got %d", len(matches))
	}
	got := text[matches[0].Start:matches[0].End]
	want := "aB3$kL9#mN2&pQ5xR8wT4yU7zV1"
	if got != want {
		t.Fatalf("match slice = %q; want %q", got, want)
	}
}
