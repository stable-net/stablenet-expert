package filter

import (
	"os"
	"strings"
	"testing"

	"github.com/stable-net/stablenet-expert/packages/jira-gateway-mcp/internal/types"
)

// resetEnv unsets any env-injected paths and clears the cache so tests start fresh.
func resetEnv(t *testing.T) {
	t.Helper()
	t.Setenv("PATTERNS_PATH", "")
	os.Unsetenv("PATTERNS_PATH")
	os.Unsetenv("CUSTOM_PATTERNS_PATH")
	ResetCache()
}

func TestScanAndFilter_CleanBenignText(t *testing.T) {
	resetEnv(t)
	r := ScanAndFilter("This is just a normal ticket description.")
	if r.Metadata.ScanResult != types.ScanClean {
		t.Fatalf("scan_result = %s; want CLEAN", r.Metadata.ScanResult)
	}
	if r.Metadata.RedactedCount != 0 {
		t.Fatalf("redacted_count = %d; want 0", r.Metadata.RedactedCount)
	}
	if r.Text != "This is just a normal ticket description." {
		t.Fatalf("text = %q; want unchanged", r.Text)
	}
}

func TestScanAndFilter_BlocksPEMPrivateKey(t *testing.T) {
	resetEnv(t)
	text := "Here is a key:\n-----BEGIN RSA PRIVATE KEY-----\nABC\n-----END RSA PRIVATE KEY-----"
	r := ScanAndFilter(text)
	if r.Metadata.ScanResult != types.ScanBlocked {
		t.Fatalf("scan_result = %s; want BLOCKED", r.Metadata.ScanResult)
	}
	if r.Text != "" {
		t.Fatalf("text should be empty when blocked, got %q", r.Text)
	}
	if !contains(r.Metadata.BlockedPatterns, "private_key_pem") {
		t.Fatalf("blocked_patterns = %v; want to contain private_key_pem", r.Metadata.BlockedPatterns)
	}
}

func TestScanAndFilter_BlocksGCPServiceAccountJSON(t *testing.T) {
	resetEnv(t)
	r := ScanAndFilter(`{"type": "service_account", "project_id": "test"}`)
	if r.Metadata.ScanResult != types.ScanBlocked {
		t.Fatalf("scan_result = %s; want BLOCKED", r.Metadata.ScanResult)
	}
}

func TestScanAndFilter_RedactsAWSAccessKey(t *testing.T) {
	resetEnv(t)
	r := ScanAndFilter("credentials: AKIAIOSFODNN7EXAMPLE in config")
	if r.Metadata.ScanResult != types.ScanRedacted {
		t.Fatalf("scan_result = %s; want REDACTED", r.Metadata.ScanResult)
	}
	if !strings.Contains(r.Text, "[REDACTED:aws_access_key]") {
		t.Fatalf("text = %q; want to contain [REDACTED:aws_access_key]", r.Text)
	}
	if strings.Contains(r.Text, "AKIAIOSFODNN7EXAMPLE") {
		t.Fatalf("text still contains the original secret: %q", r.Text)
	}
}

func TestScanAndFilter_RedactsOpenAIKey(t *testing.T) {
	resetEnv(t)
	r := ScanAndFilter("key=sk-1234567890abcdefghijklmnop")
	if r.Metadata.ScanResult != types.ScanRedacted {
		t.Fatalf("scan_result = %s; want REDACTED", r.Metadata.ScanResult)
	}
	if strings.Contains(r.Text, "sk-1234567890abcdefghijklmnop") {
		t.Fatalf("text still contains the original secret")
	}
}

func TestScanAndFilter_RedactsDBConnectionString(t *testing.T) {
	resetEnv(t)
	r := ScanAndFilter("DSN: postgres://admin:s3cret@db.internal:5432/prod")
	if r.Metadata.ScanResult != types.ScanRedacted {
		t.Fatalf("scan_result = %s; want REDACTED", r.Metadata.ScanResult)
	}
	if strings.Contains(r.Text, "s3cret") {
		t.Fatalf("text still contains password substring")
	}
}

func TestScanAndFilter_RedactsInternalIP(t *testing.T) {
	resetEnv(t)
	r := ScanAndFilter("Connect to 10.0.1.5:5432")
	if r.Metadata.ScanResult != types.ScanRedacted {
		t.Fatalf("scan_result = %s; want REDACTED", r.Metadata.ScanResult)
	}
	if !strings.Contains(r.Text, "[REDACTED:ip_address_internal]") {
		t.Fatalf("text = %q; want internal IP redaction", r.Text)
	}
}

func TestScanAndFilter_MultiplePatternsOneText(t *testing.T) {
	resetEnv(t)
	r := ScanAndFilter("AWS=AKIAIOSFODNN7EXAMPLE and OpenAI=sk-abcdefghij1234567890xyz")
	if r.Metadata.ScanResult != types.ScanRedacted {
		t.Fatalf("scan_result = %s; want REDACTED", r.Metadata.ScanResult)
	}
	if r.Metadata.RedactedCount < 2 {
		t.Fatalf("redacted_count = %d; want >= 2", r.Metadata.RedactedCount)
	}
}

func TestScanAndFilter_BlockTakesPrecedenceOverRedact(t *testing.T) {
	resetEnv(t)
	text := "key=AKIAIOSFODNN7EXAMPLE\n-----BEGIN OPENSSH PRIVATE KEY-----\nABC\n-----END OPENSSH PRIVATE KEY-----"
	r := ScanAndFilter(text)
	if r.Metadata.ScanResult != types.ScanBlocked {
		t.Fatalf("scan_result = %s; want BLOCKED", r.Metadata.ScanResult)
	}
	if r.Text != "" {
		t.Fatalf("text should be empty when blocked")
	}
}

func TestScanAndFilter_EmptyString(t *testing.T) {
	resetEnv(t)
	r := ScanAndFilter("")
	if r.Metadata.ScanResult != types.ScanClean {
		t.Fatalf("scan_result = %s; want CLEAN for empty", r.Metadata.ScanResult)
	}
}

func TestScanAndFilter_FailSafeOnMissingPatternsFile(t *testing.T) {
	resetEnv(t)
	t.Setenv("PATTERNS_PATH", "/nonexistent/path/patterns.json")
	ResetCache()
	defer func() {
		os.Unsetenv("PATTERNS_PATH")
		ResetCache()
	}()

	r := ScanAndFilter("any text")
	if r.Metadata.ScanResult != types.ScanBlocked {
		t.Fatalf("scan_result = %s; want BLOCKED (fail-safe)", r.Metadata.ScanResult)
	}
	if !contains(r.Metadata.BlockedPatterns, "filter_engine_error") {
		t.Fatalf("blocked_patterns = %v; want to contain filter_engine_error", r.Metadata.BlockedPatterns)
	}
	if r.Text != "" {
		t.Fatalf("text should be empty on fail-safe block")
	}
}

func TestScanAndFilter_BlocksOversizedPayload(t *testing.T) {
	resetEnv(t)
	huge := strings.Repeat("x", 2_000_000)
	r := ScanAndFilter(huge)
	if r.Metadata.ScanResult != types.ScanBlocked {
		t.Fatalf("scan_result = %s; want BLOCKED for oversized", r.Metadata.ScanResult)
	}
}

// --- MergeMetadata ---

func TestMergeMetadata_AllCleanStaysClean(t *testing.T) {
	resetEnv(t)
	a := ScanAndFilter("hello").Metadata
	b := ScanAndFilter("world").Metadata
	merged := MergeMetadata(a, b)
	if merged.ScanResult != types.ScanClean {
		t.Fatalf("scan_result = %s; want CLEAN", merged.ScanResult)
	}
}

func TestMergeMetadata_AnyRedactedBecomesRedacted(t *testing.T) {
	resetEnv(t)
	clean := ScanAndFilter("hello").Metadata
	red := ScanAndFilter("AKIAIOSFODNN7EXAMPLE").Metadata
	merged := MergeMetadata(clean, red)
	if merged.ScanResult != types.ScanRedacted {
		t.Fatalf("scan_result = %s; want REDACTED", merged.ScanResult)
	}
}

func TestMergeMetadata_BlockedWins(t *testing.T) {
	resetEnv(t)
	clean := ScanAndFilter("hello").Metadata
	red := ScanAndFilter("AKIAIOSFODNN7EXAMPLE").Metadata
	blk := ScanAndFilter("-----BEGIN RSA PRIVATE KEY-----\nXXX\n-----END RSA PRIVATE KEY-----").Metadata
	merged := MergeMetadata(clean, red, blk)
	if merged.ScanResult != types.ScanBlocked {
		t.Fatalf("scan_result = %s; want BLOCKED", merged.ScanResult)
	}
}

func TestMergeMetadata_AccumulatesRedactedCount(t *testing.T) {
	resetEnv(t)
	a := ScanAndFilter("AKIAIOSFODNN7EXAMPLE").Metadata
	b := ScanAndFilter("sk-abcdefghij1234567890xyz").Metadata
	merged := MergeMetadata(a, b)
	want := a.RedactedCount + b.RedactedCount
	if merged.RedactedCount != want {
		t.Fatalf("redacted_count = %d; want %d", merged.RedactedCount, want)
	}
}

// --- helpers ---

func contains(haystack []string, needle string) bool {
	for _, s := range haystack {
		if s == needle {
			return true
		}
	}
	return false
}
