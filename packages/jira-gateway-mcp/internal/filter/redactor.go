package filter

import (
	"sort"
	"strings"

	"github.com/0xmhha/stablenet-expert/packages/jira-gateway-mcp/internal/types"
)

// redact replaces matched ranges with config.RedactReplacement (after
// substituting {pattern_id}). Overlapping matches resolve to the outer match.
func redact(text string, matches []types.FilterMatch, config types.PatternsConfig) string {
	if len(matches) == 0 {
		return text
	}

	// Greedy outer-wins: process largest range first so the outer match claims
	// its territory before any inner matches can.
	byLength := make([]types.FilterMatch, len(matches))
	copy(byLength, matches)
	sort.SliceStable(byLength, func(i, j int) bool {
		li := byLength[i].End - byLength[i].Start
		lj := byLength[j].End - byLength[j].Start
		if li != lj {
			return li > lj
		}
		return byLength[i].Start < byLength[j].Start
	})

	deduped := make([]types.FilterMatch, 0, len(byLength))
	for _, m := range byLength {
		overlaps := false
		for _, d := range deduped {
			if m.Start < d.End && m.End > d.Start {
				overlaps = true
				break
			}
		}
		if !overlaps {
			deduped = append(deduped, m)
		}
	}

	// Replace from end to start so positions stay valid.
	sort.SliceStable(deduped, func(i, j int) bool {
		return deduped[i].Start > deduped[j].Start
	})

	result := text
	for _, m := range deduped {
		replacement := strings.ReplaceAll(config.RedactReplacement, "{pattern_id}", m.PatternID)
		result = result[:m.Start] + replacement + result[m.End:]
	}
	return result
}
