"""test_stablenet_knowledge_client.py — unit tests for the HTTP StablenetKnowledgeClient.

The client speaks MCP over Streamable HTTP now, so these tests monkeypatch
_post / _call (no live server) and cover: tool-name mapping, JSON-RPC result
unwrapping (structuredContent preferred, text fallback, RPC error), SSE vs
plain-JSON body parsing, the connected gate, and env-based construction.
"""

from __future__ import annotations

import json
import os
import sys
import unittest

_BENCH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BENCH_ROOT not in sys.path:
    sys.path.insert(0, _BENCH_ROOT)

from stablenet_knowledge_client import (  # noqa: E402
    StablenetKnowledgeClient,
    _TOOL_NAME_MAP,
    _first_jsonrpc_object,
    make_stablenet_knowledge_client_from_env,
)


class TestToolNameMap(unittest.TestCase):
    def test_short_names_map_to_full(self):
        self.assertEqual(_TOOL_NAME_MAP["get_for_task"], "cks.context.get_for_task")
        self.assertEqual(_TOOL_NAME_MAP["find_symbol"], "cks.context.find_symbol")
        self.assertEqual(_TOOL_NAME_MAP["semantic_search"], "cks.context.semantic_search")

    def test_flow_tools_mapped(self):
        for s in ("get_flow", "expand_flow", "find_branches", "get_invariant_enforcement"):
            self.assertEqual(_TOOL_NAME_MAP[s], f"cks.context.{s}")

    def test_full_names_pass_through(self):
        self.assertEqual(_TOOL_NAME_MAP["cks.context.get_for_task"], "cks.context.get_for_task")

    def test_unknown_short_name_not_in_map(self):
        self.assertNotIn("nonexistent_tool", _TOOL_NAME_MAP)


class TestFirstJSONRPCObject(unittest.TestCase):
    def test_plain_json(self):
        obj = _first_jsonrpc_object('{"jsonrpc":"2.0","id":1,"result":{}}')
        self.assertEqual(obj["id"], 1)

    def test_sse_data_line(self):
        body = 'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"ok":true}}\n\n'
        obj = _first_jsonrpc_object(body)
        self.assertEqual(obj["id"], 2)
        self.assertTrue(obj["result"]["ok"])

    def test_empty_and_invalid(self):
        self.assertIsNone(_first_jsonrpc_object(""))
        self.assertIsNone(_first_jsonrpc_object("not json {"))


class TestCallUnwrapping(unittest.TestCase):
    """_call unwraps a JSON-RPC object returned by _post."""

    def _client(self, canned):
        c = StablenetKnowledgeClient("http://test/mcp")
        c._post = lambda payload, expect_result=True: canned  # type: ignore[assignment]
        return c

    def test_structured_content_preferred(self):
        structured = {"citations": [{"file": "foo.go", "start_line": 1}]}
        c = self._client({"jsonrpc": "2.0", "id": 1, "result": {
            "content": [{"type": "text", "text": "plain fallback"}],
            "structuredContent": structured,
        }})
        self.assertEqual(c._call("cks.context.find_symbol", {"name": "Foo"}), structured)

    def test_text_fallback_parsed_as_json(self):
        inner = {"query": "q", "citations": []}
        c = self._client({"jsonrpc": "2.0", "id": 1, "result": {
            "content": [{"type": "text", "text": json.dumps(inner)}],
        }})
        self.assertEqual(c._call("cks.context.get_for_task", {"prompt": "q"}), inner)

    def test_text_fallback_plain_string(self):
        c = self._client({"jsonrpc": "2.0", "id": 1, "result": {
            "content": [{"type": "text", "text": "evidence pack"}],
        }})
        self.assertEqual(c._call("cks.context.get_for_task", {"prompt": "q"}), {"text": "evidence pack"})

    def test_rpc_error_returns_error_dict(self):
        c = self._client({"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "tool not found"}})
        result = c._call("cks.context.find_symbol", {"name": "X"})
        self.assertIn("error", result)
        self.assertIn("tool not found", result["error"])

    def test_transport_error_passes_through(self):
        # _post itself failed (HTTP/URL error) → surfaced as an error dict.
        c = self._client({"error": "stablenet-knowledge HTTP error: connection refused"})
        result = c._call("cks.context.find_symbol", {"name": "X"})
        self.assertIn("error", result)
        self.assertIn("connection refused", result["error"])


class TestPublicCallable(unittest.TestCase):
    def test_unknown_tool_returns_error(self):
        c = StablenetKnowledgeClient("http://test/mcp")
        c._connected = True
        result = c("nonexistent_tool", {})
        self.assertIn("error", result)
        self.assertIn("unknown stablenet-knowledge tool", result["error"])

    def test_not_connected_returns_error(self):
        c = StablenetKnowledgeClient("http://test/mcp")  # _connected defaults False
        result = c("get_for_task", {"prompt": "q"})
        self.assertIn("error", result)
        self.assertIn("not connected", result["error"])

    def test_connected_happy_path(self):
        c = StablenetKnowledgeClient("http://test/mcp")
        c._connected = True
        c._call = lambda name, args: {"citations": [{"file": "validator.go"}]}  # type: ignore[assignment]
        result = c("find_symbol", {"name": "QuorumSize"})
        self.assertEqual(result, {"citations": [{"file": "validator.go"}]})


class TestMakeFromEnv(unittest.TestCase):
    def test_reads_cks_mcp_url(self):
        prev = os.environ.get("STABLENET_KNOWLEDGE_MCP_URL")
        try:
            os.environ["STABLENET_KNOWLEDGE_MCP_URL"] = "http://example:8080/mcp"
            c = make_stablenet_knowledge_client_from_env()
            self.assertIsNotNone(c)
            self.assertEqual(c._url, "http://example:8080/mcp")
        finally:
            if prev is None:
                os.environ.pop("STABLENET_KNOWLEDGE_MCP_URL", None)
            else:
                os.environ["STABLENET_KNOWLEDGE_MCP_URL"] = prev

    def test_none_when_unset(self):
        prev = os.environ.pop("STABLENET_KNOWLEDGE_MCP_URL", None)
        try:
            self.assertIsNone(make_stablenet_knowledge_client_from_env())
        finally:
            if prev is not None:
                os.environ["STABLENET_KNOWLEDGE_MCP_URL"] = prev


if __name__ == "__main__":
    unittest.main()
