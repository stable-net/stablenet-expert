"""stablenet_knowledge_client.py — MCP **HTTP** client for the Code Knowledge System (stablenet-knowledge).

Connects to a running stablenet-knowledge-mcp Streamable-HTTP server (started out of band, e.g.
by code-knowledge-system/scripts/serve-cks-http.sh) and exposes a single
callable matching the ``cks_tool(tool_name, args_dict) -> dict`` contract that
methods/scorers expect.

Why HTTP (not a spawned stdio subprocess): the bench MUST measure the SAME stablenet-knowledge
instance/index that everything else uses. Spawning a private stdio subprocess
with its own config risked pointing the bench at a different dataset than the
live server — silently contaminating results. Connecting by URL to the one
shared server removes that ambiguity; ``identity()`` (cks.ops.health) records
exactly which instance/index/commit the bench talked to.

Endpoint comes from the environment, never the repo: set ``STABLENET_KNOWLEDGE_MCP_URL`` (e.g.
``http://<ip>:<port>/mcp``) in your shell / ~/.claude/settings.json. No ip:port
is hardcoded here, so nothing environment-specific or network-topology-revealing
lands in git.

Short name → full MCP tool name mapping covers the graph, search, and flow tools.

Usage::

    with StablenetKnowledgeClient(url) as cks:
        result = cks("get_for_task", {"prompt": "..."})
        flow   = cks("get_flow", {"flow_id": "ep-cli-init"})

On any failure the callable returns a structured error dict (never raises), so
methods degrade gracefully to ``cks_partial``.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


# Map short names used by methods to fully-qualified MCP tool names.
_SHORT_TOOLS = [
    "get_for_task",
    "get_subgraph",
    "find_symbol",
    "find_callers",
    "find_callees",
    "semantic_search",
    "search_text",
    "change_history",
    "impact_analysis",
    "concurrency_impact",
    # Phase D flow-aware tools
    "get_flow",
    "expand_flow",
    "find_branches",
    "get_invariant_enforcement",
]
_TOOL_NAME_MAP: Dict[str, str] = {}
for _s in _SHORT_TOOLS:
    _full = f"cks.context.{_s}"
    _TOOL_NAME_MAP[_s] = _full
    _TOOL_NAME_MAP[_full] = _full  # fully-qualified names pass through unchanged

_DEFAULT_TIMEOUT = 30  # seconds per tool call


class StablenetKnowledgeClient:
    """MCP Streamable-HTTP client for a running stablenet-knowledge-mcp server.

    Parameters
    ----------
    url : str
        The stablenet-knowledge-mcp MCP endpoint, e.g. ``http://127.0.0.1:8080/mcp``.
    timeout : int
        Per-call timeout in seconds. Default 30.
    """

    def __init__(self, url: str, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self._url = url
        self._timeout = timeout
        self._session_id: Optional[str] = None
        self._lock = threading.Lock()
        self._req_id = 0
        self._connected = False
        self.identity: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "StablenetKnowledgeClient":
        self._start()
        return self

    def __exit__(self, *_: Any) -> None:
        # HTTP is connectionless per request; nothing to tear down. The shared
        # server keeps running (it is not owned by the bench).
        self._connected = False

    # ------------------------------------------------------------------
    # Internal lifecycle
    # ------------------------------------------------------------------

    def _start(self) -> None:
        """Run the MCP initialize handshake and record instance identity."""
        init = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "stablenet-knowledge-bench", "version": "0.1"},
            },
        })
        if "error" in init:
            # Leave _connected False; __call__ will report the connection error.
            print(f"stablenet-knowledge: connect failed at {self._url}: {init['error']}", file=sys.stderr)
            return
        # notifications/initialized carries no id and expects no body.
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                   expect_result=False)
        self._connected = True
        # Record + announce which instance/index the bench is measuring, so the
        # run is self-documenting (transparency: no hidden divergence).
        health = self._call("cks.ops.health", {})
        if isinstance(health, dict) and "error" not in health:
            self.identity = health
            ckv = (health.get("backends") or {}).get("ckv") or {}
            print(
                "stablenet-knowledge: connected {url} name={name} indexed_head={head} "
                "model={model} serviceable={svc}".format(
                    url=self._url,
                    name=health.get("name", "?"),
                    head=ckv.get("indexed_head", "?"),
                    model=ckv.get("model", "?"),
                    svc=health.get("serviceable"),
                ),
                file=sys.stderr,
            )

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _post(self, payload: Dict[str, Any], expect_result: bool = True) -> Dict[str, Any]:
        """POST one JSON-RPC message; return the parsed JSON-RPC object.

        Handles both a plain ``application/json`` body and a Streamable-HTTP
        ``text/event-stream`` body (``data: {...}`` lines). Captures the
        Mcp-Session-Id header from the initialize response for reuse.
        """
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self._url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
        if self._session_id:
            req.add_header("Mcp-Session-Id", self._session_id)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self._session_id = sid
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            return {"error": f"stablenet-knowledge HTTP error: {exc}"}
        except Exception as exc:  # noqa: BLE001 — never raise to callers
            return {"error": f"stablenet-knowledge request error: {exc}"}

        if not expect_result:
            return {}
        obj = _first_jsonrpc_object(body)
        if obj is None:
            return {"error": "stablenet-knowledge returned no JSON-RPC object", "raw": body[:200]}
        return obj

    def _call(self, full_tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Send a tools/call request and return the unwrapped result."""
        resp = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": full_tool_name, "arguments": arguments},
        })
        if "error" in resp and "result" not in resp:
            err = resp["error"]
            if isinstance(err, dict):
                return {"error": f"stablenet-knowledge RPC error: {err.get('message', err)}"}
            return {"error": str(err) if not str(err).startswith("stablenet-knowledge ") else err}

        result = resp.get("result", {})
        structured = result.get("structuredContent")
        if structured is not None:
            return structured
        content = result.get("content", [])
        if content:
            text = content[0].get("text", "")
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {"text": text}
        return {"error": "stablenet-knowledge returned no content"}

    # ------------------------------------------------------------------
    # Public callable interface
    # ------------------------------------------------------------------

    def __call__(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Call a stablenet-knowledge tool by short or full name. Never raises."""
        full_name = _TOOL_NAME_MAP.get(tool_name)
        if full_name is None:
            return {"error": f"unknown stablenet-knowledge tool: {tool_name!r}"}
        if not self._connected:
            return {"error": "stablenet-knowledge not connected"}
        with self._lock:
            try:
                return self._call(full_name, args)
            except Exception as exc:  # noqa: BLE001
                return {"error": f"stablenet-knowledge client unexpected error: {exc}"}


def _first_jsonrpc_object(body: str) -> Optional[Dict[str, Any]]:
    """Extract the first JSON-RPC object from a plain-JSON or SSE body."""
    body = body.strip()
    if not body:
        return None
    # Streamable HTTP: one or more `data: {...}` lines (SSE framing).
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            line = line[len("data:"):].strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    # Plain JSON body.
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def make_stablenet_knowledge_client_from_env(timeout: int = _DEFAULT_TIMEOUT) -> Optional[StablenetKnowledgeClient]:
    """Construct a StablenetKnowledgeClient from the environment.

    Reads ``STABLENET_KNOWLEDGE_MCP_URL`` (e.g. ``http://<ip>:<port>/mcp``). Returns None when
    unset, so callers degrade gracefully. The endpoint is intentionally NOT
    hardcoded in the repo — it is environment/machine specific and mildly
    network-revealing, so it belongs in the shell env / settings, not git.
    """
    url = os.environ.get("STABLENET_KNOWLEDGE_MCP_URL", "").strip()
    if not url:
        return None
    return StablenetKnowledgeClient(url=url, timeout=timeout)
