package jira

import (
	"encoding/json"
	"strings"
	"testing"
)

func parseADF(t *testing.T, s string) any {
	t.Helper()
	var v any
	if err := json.Unmarshal([]byte(s), &v); err != nil {
		t.Fatalf("parseADF: %v", err)
	}
	return v
}

func TestADFToMarkdown_PlainParagraph(t *testing.T) {
	in := parseADF(t, `{
		"type": "doc", "version": 1,
		"content": [{"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}]}]
	}`)
	got := ADFToMarkdown(in)
	if got != "Hello world" {
		t.Fatalf("got %q; want %q", got, "Hello world")
	}
}

func TestADFToMarkdown_Heading(t *testing.T) {
	in := parseADF(t, `{
		"type": "doc",
		"content": [{
			"type": "heading", "attrs": {"level": 2},
			"content": [{"type": "text", "text": "Background"}]
		}]
	}`)
	got := ADFToMarkdown(in)
	if got != "## Background" {
		t.Fatalf("got %q; want %q", got, "## Background")
	}
}

func TestADFToMarkdown_BulletList(t *testing.T) {
	in := parseADF(t, `{
		"type": "doc",
		"content": [{
			"type": "bulletList",
			"content": [
				{"type": "listItem", "content": [
					{"type": "paragraph", "content": [{"type":"text","text":"first"}]}
				]},
				{"type": "listItem", "content": [
					{"type": "paragraph", "content": [{"type":"text","text":"second"}]}
				]}
			]
		}]
	}`)
	got := ADFToMarkdown(in)
	want := "- first\n- second"
	if got != want {
		t.Fatalf("got %q; want %q", got, want)
	}
}

func TestADFToMarkdown_OrderedList(t *testing.T) {
	in := parseADF(t, `{
		"type": "doc",
		"content": [{
			"type": "orderedList",
			"content": [
				{"type":"listItem","content":[{"type":"paragraph","content":[{"type":"text","text":"a"}]}]},
				{"type":"listItem","content":[{"type":"paragraph","content":[{"type":"text","text":"b"}]}]}
			]
		}]
	}`)
	got := ADFToMarkdown(in)
	want := "1. a\n2. b"
	if got != want {
		t.Fatalf("got %q; want %q", got, want)
	}
}

func TestADFToMarkdown_TaskList(t *testing.T) {
	in := parseADF(t, `{
		"type": "doc",
		"content": [{
			"type": "taskList",
			"content": [
				{"type":"taskItem","attrs":{"state":"DONE"},"content":[{"type":"text","text":"done"}]},
				{"type":"taskItem","attrs":{"state":"TODO"},"content":[{"type":"text","text":"todo"}]}
			]
		}]
	}`)
	got := ADFToMarkdown(in)
	if !strings.Contains(got, "- [x] done") || !strings.Contains(got, "- [ ] todo") {
		t.Fatalf("got %q; want checkbox lines", got)
	}
}

func TestADFToMarkdown_CodeBlock(t *testing.T) {
	in := parseADF(t, `{
		"type": "doc",
		"content": [{
			"type": "codeBlock", "attrs": {"language": "go"},
			"content": [{"type":"text","text":"package main"}]
		}]
	}`)
	got := ADFToMarkdown(in)
	want := "```go\npackage main\n```"
	if got != want {
		t.Fatalf("got %q; want %q", got, want)
	}
}

func TestADFToMarkdown_MarksStrongAndEm(t *testing.T) {
	in := parseADF(t, `{
		"type": "doc",
		"content": [{
			"type":"paragraph",
			"content": [
				{"type":"text","text":"bold","marks":[{"type":"strong"}]},
				{"type":"text","text":" and "},
				{"type":"text","text":"italic","marks":[{"type":"em"}]}
			]
		}]
	}`)
	got := ADFToMarkdown(in)
	if got != "**bold** and *italic*" {
		t.Fatalf("got %q; want %q", got, "**bold** and *italic*")
	}
}

func TestADFToMarkdown_NilReturnsEmpty(t *testing.T) {
	if got := ADFToMarkdown(nil); got != "" {
		t.Fatalf("got %q; want empty", got)
	}
}

func TestADFToMarkdown_UnknownNodePreservesText(t *testing.T) {
	in := parseADF(t, `{
		"type": "doc",
		"content": [{
			"type": "futureUnknownNode",
			"content": [{"type":"text","text":"survives"}]
		}]
	}`)
	got := ADFToMarkdown(in)
	if got != "survives" {
		t.Fatalf("got %q; want %q", got, "survives")
	}
}
