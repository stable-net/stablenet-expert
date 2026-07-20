// Package filter implements the sensitive-information filter engine.
package filter

import (
	"math"
	"regexp"

	"github.com/0xmhha/stablenet-expert/packages/jira-gateway-mcp/internal/types"
)

// shannonEntropy returns the Shannon entropy of s in bits per character.
// 0 for empty or single-character-class strings; higher means more random.
func shannonEntropy(s string) float64 {
	if len(s) == 0 {
		return 0
	}
	counts := make(map[rune]int, len(s))
	total := 0
	for _, r := range s {
		counts[r]++
		total++
	}
	if total == 0 {
		return 0
	}
	h := 0.0
	for _, c := range counts {
		p := float64(c) / float64(total)
		h -= p * math.Log2(p)
	}
	return h
}

// tokenSplit splits text into candidate tokens by whitespace and common
// delimiters. We avoid eating high-entropy strings so the entropy detector
// can see them intact.
var tokenSplitRegex = regexp.MustCompile(`[^\s'"(),=:;<>{}\[\]]+`)

// scanEntropy returns matches for high-entropy tokens that pass length and
// exclude-pattern filters. Returned positions are byte offsets in the input.
func scanEntropy(text string, p types.Pattern) []types.FilterMatch {
	excludeRegexes := make([]*regexp.Regexp, 0, len(p.ExcludePatterns))
	for _, raw := range p.ExcludePatterns {
		re, err := regexp.Compile(raw)
		if err != nil {
			// Skip malformed exclude patterns; conservative — false positives
			// are preferable to silently bypassing the entire detector.
			continue
		}
		excludeRegexes = append(excludeRegexes, re)
	}

	matches := []types.FilterMatch{}
	for _, loc := range tokenSplitRegex.FindAllStringIndex(text, -1) {
		token := text[loc[0]:loc[1]]
		length := len(token)
		if length < p.MinLength || length > p.MaxLength {
			continue
		}
		excluded := false
		for _, re := range excludeRegexes {
			if re.MatchString(token) {
				excluded = true
				break
			}
		}
		if excluded {
			continue
		}
		if shannonEntropy(token) >= p.Threshold {
			matches = append(matches, types.FilterMatch{
				PatternID: p.ID,
				Severity:  p.Severity,
				Action:    p.Action,
				Start:     loc[0],
				End:       loc[1],
			})
		}
	}
	return matches
}

