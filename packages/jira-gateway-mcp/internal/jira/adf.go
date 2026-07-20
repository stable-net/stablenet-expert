// Package jira provides a Jira Cloud REST API v3 client with ADF→Markdown
// conversion. The client is intentionally thin — it does not apply filters
// or any other policy. Filtering happens in the server layer.
package jira

import (
	"fmt"
	"strings"
)

// ADFNode represents one node in the Atlassian Document Format tree.
type adfNode struct {
	Type    string                 `json:"type"`
	Text    string                 `json:"text,omitempty"`
	Attrs   map[string]any         `json:"attrs,omitempty"`
	Content []adfNode              `json:"content,omitempty"`
	Marks   []map[string]any       `json:"marks,omitempty"`
	Extra   map[string]any         `json:"-"`
	_       struct{ _ [0]struct{} } // prevent struct comparison
}

// ADFToMarkdown converts the ADF JSON tree (typically the description field
// of a Jira issue) into a Markdown string.
//
// Supported node types cover the common subset used in tickets. Unknown nodes
// recurse into children so text content is preserved even if the structure
// is unfamiliar.
func ADFToMarkdown(adf any) string {
	if adf == nil {
		return ""
	}
	root := toNode(adf)
	return strings.TrimSpace(renderNode(root, renderCtx{listDepth: 0}))
}

type renderCtx struct {
	listDepth    int
	ordered      bool
	orderedIndex int
}

func toNode(v any) adfNode {
	m, ok := v.(map[string]any)
	if !ok {
		return adfNode{Type: "text", Text: fmt.Sprintf("%v", v)}
	}
	node := adfNode{}
	if t, ok := m["type"].(string); ok {
		node.Type = t
	}
	if t, ok := m["text"].(string); ok {
		node.Text = t
	}
	if a, ok := m["attrs"].(map[string]any); ok {
		node.Attrs = a
	}
	if c, ok := m["content"].([]any); ok {
		node.Content = make([]adfNode, 0, len(c))
		for _, child := range c {
			node.Content = append(node.Content, toNode(child))
		}
	}
	if marks, ok := m["marks"].([]any); ok {
		node.Marks = make([]map[string]any, 0, len(marks))
		for _, mk := range marks {
			if mm, ok := mk.(map[string]any); ok {
				node.Marks = append(node.Marks, mm)
			}
		}
	}
	return node
}

func renderNode(n adfNode, ctx renderCtx) string {
	switch n.Type {
	case "doc":
		return renderChildren(n, ctx, "\n\n")
	case "paragraph":
		return renderChildren(n, ctx, "")
	case "heading":
		level := 1
		if l, ok := n.Attrs["level"].(float64); ok {
			level = clamp(int(l), 1, 6)
		}
		return strings.Repeat("#", level) + " " + renderChildren(n, ctx, "")
	case "text":
		return applyMarks(n.Text, n.Marks)
	case "hardBreak":
		return "  \n"
	case "bulletList":
		ctx2 := ctx
		ctx2.ordered = false
		return renderList(n, ctx2)
	case "orderedList":
		ctx2 := ctx
		ctx2.ordered = true
		return renderList(n, ctx2)
	case "listItem":
		inner := strings.TrimSpace(renderChildren(n, ctx, "\n"))
		indent := strings.Repeat("  ", maxInt(0, ctx.listDepth-1))
		marker := "-"
		if ctx.ordered {
			marker = fmt.Sprintf("%d.", ctx.orderedIndex)
		}
		return fmt.Sprintf("%s%s %s", indent, marker, inner)
	case "taskList":
		return renderChildren(n, ctx, "\n")
	case "taskItem":
		state, _ := n.Attrs["state"].(string)
		box := "[ ]"
		if state == "DONE" {
			box = "[x]"
		}
		return fmt.Sprintf("- %s %s", box, strings.TrimSpace(renderChildren(n, ctx, "")))
	case "codeBlock":
		lang, _ := n.Attrs["language"].(string)
		return fmt.Sprintf("```%s\n%s\n```", lang, renderChildren(n, ctx, ""))
	case "blockquote":
		inner := renderChildren(n, ctx, "\n")
		lines := strings.Split(inner, "\n")
		for i, l := range lines {
			lines[i] = "> " + l
		}
		return strings.Join(lines, "\n")
	case "rule":
		return "---"
	case "table":
		return renderTable(n, ctx)
	case "tableRow", "tableHeader", "tableCell":
		return renderChildren(n, ctx, " ")
	case "mention":
		text, _ := n.Attrs["text"].(string)
		if text == "" {
			if id, ok := n.Attrs["id"].(string); ok {
				text = id
			} else {
				text = "mention"
			}
		}
		return "@" + text
	case "emoji":
		short, _ := n.Attrs["shortName"].(string)
		return short
	case "inlineCard":
		url, _ := n.Attrs["url"].(string)
		return fmt.Sprintf("<%s>", url)
	default:
		// Unknown — recurse to preserve text content.
		return renderChildren(n, ctx, "")
	}
}

func renderChildren(n adfNode, ctx renderCtx, sep string) string {
	if len(n.Content) == 0 {
		return ""
	}
	parts := make([]string, 0, len(n.Content))
	for _, c := range n.Content {
		parts = append(parts, renderNode(c, ctx))
	}
	return strings.Join(parts, sep)
}

func renderList(n adfNode, ctx renderCtx) string {
	nextDepth := ctx.listDepth + 1
	parts := make([]string, 0, len(n.Content))
	for i, item := range n.Content {
		childCtx := ctx
		childCtx.listDepth = nextDepth
		childCtx.orderedIndex = i + 1
		parts = append(parts, renderNode(item, childCtx))
	}
	return strings.Join(parts, "\n")
}

func renderTable(n adfNode, ctx renderCtx) string {
	if len(n.Content) == 0 {
		return ""
	}
	rows := make([]string, 0, len(n.Content))
	for _, row := range n.Content {
		cells := make([]string, 0, len(row.Content))
		for _, cell := range row.Content {
			cells = append(cells, strings.TrimSpace(renderChildren(cell, ctx, "")))
		}
		rows = append(rows, strings.Join(cells, " | "))
	}
	if len(rows) == 0 {
		return ""
	}
	header := rows[0]
	headerCells := strings.Count(header, "|") + 1
	separator := strings.Repeat("--- | ", headerCells)
	separator = strings.TrimSuffix(separator, " | ")
	return strings.Join(append([]string{header, separator}, rows[1:]...), "\n")
}

func applyMarks(text string, marks []map[string]any) string {
	if len(marks) == 0 {
		return text
	}
	result := text
	for _, mark := range marks {
		t, _ := mark["type"].(string)
		switch t {
		case "strong":
			result = "**" + result + "**"
		case "em":
			result = "*" + result + "*"
		case "code":
			result = "`" + result + "`"
		case "strike":
			result = "~~" + result + "~~"
		case "link":
			href := ""
			if attrs, ok := mark["attrs"].(map[string]any); ok {
				if h, ok := attrs["href"].(string); ok {
					href = h
				}
			}
			result = fmt.Sprintf("[%s](%s)", result, href)
		}
	}
	return result
}

func clamp(v, lo, hi int) int {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}
