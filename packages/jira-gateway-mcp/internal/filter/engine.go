package filter

import (
	"fmt"
	"os"
	"time"

	"github.com/0xmhha/stablenet-expert/packages/jira-gateway-mcp/internal/types"
)

// ScanAndFilter is the engine's single entrypoint. It applies all configured
// patterns to text and returns the sanitized result + metadata.
//
// Fail-safe (RI-06): any internal error returns a BLOCKED result with empty
// text. The original text is never returned when filtering fails.
func ScanAndFilter(text string) types.FilterResult {
	scannedAt := time.Now().UTC().Format(time.RFC3339)

	loaded, err := Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "[jira-gateway-mcp] filter error (fail-safe block): %v\n", err)
		return blockedResult([]string{"filter_engine_error"}, scannedAt)
	}

	if len(text) > loaded.Config.MaxScanSizeBytes {
		return blockedResult(
			[]string{fmt.Sprintf("payload_too_large:%d", len(text))},
			scannedAt,
		)
	}

	matches := scanAll(text, loaded)

	var blocking, redacting, warning []types.FilterMatch
	for _, m := range matches {
		switch m.Action {
		case types.ActionBlock:
			blocking = append(blocking, m)
		case types.ActionRedact:
			redacting = append(redacting, m)
		case types.ActionWarn:
			warning = append(warning, m)
		}
	}

	if len(blocking) > 0 {
		ids := uniquePatternIDs(blocking)
		return blockedResult(ids, scannedAt)
	}

	redactedText := redact(text, redacting, loaded.Config)
	redactedIDs := uniquePatternIDs(redacting)
	warnIDs := uniquePatternIDs(warning)
	warnings := make([]string, 0, len(warnIDs))
	for _, id := range warnIDs {
		warnings = append(warnings, "warn:"+id)
	}

	scanResult := types.ScanClean
	if len(redacting) > 0 {
		scanResult = types.ScanRedacted
	}

	return types.FilterResult{
		Text: redactedText,
		Metadata: types.FilterMetadata{
			ScanResult:       scanResult,
			RedactedCount:    len(redacting),
			RedactedPatterns: redactedIDs,
			BlockedPatterns:  []string{},
			Warnings:         warnings,
			ScannedAt:        scannedAt,
		},
	}
}

// MergeMetadata combines metadata from multiple filter results.
// BLOCKED > REDACTED > CLEAN. Counts and pattern lists are unioned.
func MergeMetadata(metas ...types.FilterMetadata) types.FilterMetadata {
	merged := types.FilterMetadata{
		ScanResult:       types.ScanClean,
		RedactedCount:    0,
		RedactedPatterns: []string{},
		BlockedPatterns:  []string{},
		Warnings:         []string{},
		ScannedAt:        time.Now().UTC().Format(time.RFC3339),
	}
	for _, m := range metas {
		merged.RedactedCount += m.RedactedCount
		merged.RedactedPatterns = unionStrings(merged.RedactedPatterns, m.RedactedPatterns)
		merged.BlockedPatterns = unionStrings(merged.BlockedPatterns, m.BlockedPatterns)
		merged.Warnings = unionStrings(merged.Warnings, m.Warnings)
		switch m.ScanResult {
		case types.ScanBlocked:
			merged.ScanResult = types.ScanBlocked
		case types.ScanRedacted:
			if merged.ScanResult != types.ScanBlocked {
				merged.ScanResult = types.ScanRedacted
			}
		}
	}
	return merged
}

func scanAll(text string, lp *LoadedPatterns) []types.FilterMatch {
	var all []types.FilterMatch
	for _, p := range lp.Patterns {
		if p.IsEntropy() {
			all = append(all, scanEntropy(text, p)...)
			continue
		}
		re := lp.regex(p.ID)
		if re == nil {
			continue
		}
		for _, loc := range re.FindAllStringIndex(text, -1) {
			all = append(all, types.FilterMatch{
				PatternID: p.ID,
				Severity:  p.Severity,
				Action:    p.Action,
				Start:     loc[0],
				End:       loc[1],
			})
		}
	}
	return all
}

func blockedResult(patterns []string, scannedAt string) types.FilterResult {
	return types.FilterResult{
		// Never return original text when blocked.
		Text: "",
		Metadata: types.FilterMetadata{
			ScanResult:       types.ScanBlocked,
			RedactedCount:    0,
			RedactedPatterns: []string{},
			BlockedPatterns:  patterns,
			Warnings:         []string{},
			ScannedAt:        scannedAt,
		},
	}
}

func uniquePatternIDs(matches []types.FilterMatch) []string {
	seen := map[string]struct{}{}
	out := []string{}
	for _, m := range matches {
		if _, ok := seen[m.PatternID]; ok {
			continue
		}
		seen[m.PatternID] = struct{}{}
		out = append(out, m.PatternID)
	}
	return out
}

func unionStrings(a, b []string) []string {
	seen := make(map[string]struct{}, len(a)+len(b))
	out := make([]string, 0, len(a)+len(b))
	for _, s := range a {
		if _, ok := seen[s]; ok {
			continue
		}
		seen[s] = struct{}{}
		out = append(out, s)
	}
	for _, s := range b {
		if _, ok := seen[s]; ok {
			continue
		}
		seen[s] = struct{}{}
		out = append(out, s)
	}
	return out
}
