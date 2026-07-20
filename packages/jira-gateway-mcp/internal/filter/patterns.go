package filter

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"sync"

	"github.com/0xmhha/stablenet-expert/packages/jira-gateway-mcp/internal/types"
)

// resolvePatternsPath returns the path to packages/shared-patterns/patterns.json.
// Resolution order: PATTERNS_PATH env > project-root probe > cwd/packages/shared-patterns.
func resolvePatternsPath() (string, error) {
	if env := os.Getenv("PATTERNS_PATH"); env != "" {
		return filepath.Clean(env), nil
	}

	// _, file, _, _ = runtime.Caller; file is .../internal/filter/patterns.go
	_, file, _, ok := runtime.Caller(0)
	if ok {
		// internal/filter → 4 levels up reaches stablenet-expert/
		// stablenet-expert/packages/shared-patterns/patterns.json
		candidate := filepath.Clean(
			filepath.Join(filepath.Dir(file), "..", "..", "..", "..", "packages", "shared-patterns", "patterns.json"),
		)
		if _, err := os.Stat(candidate); err == nil {
			return candidate, nil
		}
	}

	if cwd, err := os.Getwd(); err == nil {
		candidate := filepath.Join(cwd, "packages", "shared-patterns", "patterns.json")
		if _, err := os.Stat(candidate); err == nil {
			return candidate, nil
		}
	}

	return "", errors.New(
		"patterns.json not found; set PATTERNS_PATH env var or run from project root",
	)
}

// resolveCustomPatternsPath returns the optional override file path.
func resolveCustomPatternsPath() string {
	if env := os.Getenv("CUSTOM_PATTERNS_PATH"); env != "" {
		if _, err := os.Stat(env); err == nil {
			return env
		}
		return ""
	}
	if cwd, err := os.Getwd(); err == nil {
		def := filepath.Join(cwd, ".stablenet-expert", "custom-patterns.json")
		if _, err := os.Stat(def); err == nil {
			return def
		}
	}
	return ""
}

// loadAndValidate reads a patterns file from disk. Performs minimal structural
// validation; specific regex compilation happens lazily in the engine.
func loadAndValidate(path string) (*types.PatternsFile, error) {
	raw, err := os.ReadFile(path) //nolint:gosec // path is resolved by us
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", path, err)
	}
	var pf types.PatternsFile
	if err := json.Unmarshal(raw, &pf); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	if len(pf.Patterns) == 0 {
		return nil, fmt.Errorf("%s: patterns array is empty", path)
	}
	for i, p := range pf.Patterns {
		if p.ID == "" {
			return nil, fmt.Errorf("%s: patterns[%d]: id is required", path, i)
		}
		if p.IsEntropy() {
			if p.MinLength <= 0 || p.MaxLength <= 0 || p.Threshold <= 0 {
				return nil, fmt.Errorf(
					"%s: patterns[%d] (%s): entropy pattern requires min_length, max_length, threshold",
					path, i, p.ID,
				)
			}
		} else if p.Regex == "" {
			return nil, fmt.Errorf(
				"%s: patterns[%d] (%s): regex required for non-entropy pattern",
				path, i, p.ID,
			)
		}
	}
	return &pf, nil
}

// mergeByID overrides base entries with custom ones sharing the same ID and
// appends new IDs. Order: base ids retain position, new custom ids appended.
func mergeByID(base, custom []types.Pattern) []types.Pattern {
	index := make(map[string]int, len(base))
	merged := make([]types.Pattern, len(base))
	copy(merged, base)
	for i, p := range base {
		index[p.ID] = i
	}
	for _, p := range custom {
		if idx, ok := index[p.ID]; ok {
			merged[idx] = p
		} else {
			index[p.ID] = len(merged)
			merged = append(merged, p)
		}
	}
	return merged
}

// LoadedPatterns is the cached, ready-to-use pattern set + compiled regexes.
type LoadedPatterns struct {
	Patterns []types.Pattern
	Config   types.PatternsConfig
	regexes  map[string]*regexp.Regexp
}

var (
	cache    *LoadedPatterns
	cacheErr error
	cacheMu  sync.Mutex
)

// ResetCache forces the next Load call to re-read patterns from disk. Tests.
func ResetCache() {
	cacheMu.Lock()
	defer cacheMu.Unlock()
	cache = nil
	cacheErr = nil
}

// Load reads patterns from shared/patterns.json + optional custom overrides,
// compiles regex patterns once, and caches the result.
func Load() (*LoadedPatterns, error) {
	cacheMu.Lock()
	defer cacheMu.Unlock()
	if cache != nil {
		return cache, nil
	}
	if cacheErr != nil {
		return nil, cacheErr
	}

	basePath, err := resolvePatternsPath()
	if err != nil {
		cacheErr = err
		return nil, err
	}
	base, err := loadAndValidate(basePath)
	if err != nil {
		cacheErr = err
		return nil, err
	}

	patterns := base.Patterns
	if customPath := resolveCustomPatternsPath(); customPath != "" {
		custom, cerr := loadAndValidate(customPath)
		if cerr != nil {
			// Custom file is optional — log to stderr and continue with base.
			fmt.Fprintf(os.Stderr,
				"[jira-gateway-mcp] warning: failed to load custom patterns from %s: %v\n",
				customPath, cerr,
			)
		} else {
			patterns = mergeByID(base.Patterns, custom.Patterns)
		}
	}

	regexes := make(map[string]*regexp.Regexp, len(patterns))
	for _, p := range patterns {
		if p.IsEntropy() {
			continue
		}
		re, err := regexp.Compile(p.Regex)
		if err != nil {
			cacheErr = fmt.Errorf("compile pattern %s: %w", p.ID, err)
			return nil, cacheErr
		}
		regexes[p.ID] = re
	}

	cache = &LoadedPatterns{
		Patterns: patterns,
		Config:   base.Config,
		regexes:  regexes,
	}
	return cache, nil
}

// regex returns the compiled regex for the given pattern id (entropy returns nil).
func (lp *LoadedPatterns) regex(id string) *regexp.Regexp {
	return lp.regexes[id]
}
