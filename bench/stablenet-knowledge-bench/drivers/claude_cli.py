"""claude_cli.py — live Claude CLI driver for the CKG Benchmark harness.

Wraps the local ``claude`` CLI binary.  Each call:
  1. Builds a combined context string: system_prompt + user_prompt.
  2. Calls: claude -p --output-format json [--append-system-prompt <sys>]
     with the user prompt passed via STDIN (positional arg).
  3. Parses the JSON response field ``.result`` (assistant text).
  4. Returns AskResult with:
     - ``input_tokens``  = CLI-billed input_tokens (includes ~20k Claude Code
       system-prompt overhead; kept for cost accounting).
     - ``injected_tokens`` = len(system_prompt + user_prompt) // 4 (harness-
       injected context only; used for the info_volume metric so M1-vs-M4
       comparisons are fair).

For M3 multi-turn: the driver iterates up to max_turns; if tool_broker is
set, it calls broker(tool_name, args) for each Python-driven tool call and
feeds the result back as the next user message, accumulating injected_tokens
across turns.

The driver never raises — errors are surfaced via AskResult.error.

CLI JSON output shape (claude -p --output-format json):
  {
    "type": "result",
    "is_error": false,
    "result": "<assistant text>",
    "usage": {
      "input_tokens": <int>,
      "output_tokens": <int>,
      ...
    },
    "total_cost_usd": <float>,
    "num_turns": <int>,
    ...
  }
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional

from .base import AskResult, Driver, ToolCall


_DEFAULT_TIMEOUT = 120  # seconds per turn


def _count_injected_tokens(system_prompt: str, user_prompt: str) -> int:
    """Estimate token count for harness-injected context via len // 4."""
    return (len(system_prompt) + len(user_prompt)) // 4


class ClaudeCLIDriver(Driver):
    """Drive the local Claude CLI binary.

    Parameters
    ----------
    claude_bin : str
        Path to the ``claude`` binary. Defaults to ``"claude"`` (on PATH).
    timeout : int
        Timeout in seconds per turn. Default 120.
    model : str, optional
        Model name to pass as ``--model``. If None, uses CLI default.
    transcript_dir : str, optional
        If set, writes JSONL transcripts to this directory.
    """

    name = "claude_cli"

    def __init__(
        self,
        claude_bin: str = "claude",
        timeout: int = _DEFAULT_TIMEOUT,
        model: Optional[str] = None,
        transcript_dir: Optional[str] = None,
    ) -> None:
        self._claude_bin = claude_bin
        self._timeout = timeout
        self._model = model
        self._transcript_dir = transcript_dir

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_cmd(self, system_prompt: str) -> List[str]:
        """Build the CLI command.  User prompt is piped via STDIN."""
        cmd = [self._claude_bin, "-p", "--output-format", "json"]
        if system_prompt:
            cmd += ["--append-system-prompt", system_prompt]
        if self._model:
            cmd += ["--model", self._model]
        return cmd

    def _run_turn(
        self, system_prompt: str, user_message: str
    ) -> Dict[str, Any]:
        """Run a single CLI turn; returns parsed JSON or a synthetic error dict."""
        cmd = self._build_cmd(system_prompt)
        try:
            result = subprocess.run(
                cmd,
                input=user_message,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            return {"error": f"timeout after {self._timeout}s", "raw": ""}
        except FileNotFoundError:
            return {
                "error": (
                    f"claude CLI binary not found: {self._claude_bin!r}. "
                    "Install Claude CLI or use --driver replay."
                ),
                "raw": "",
            }

        if result.returncode != 0:
            return {
                "error": (
                    f"claude CLI exit {result.returncode}: "
                    f"{result.stderr.strip()[:500]}"
                ),
                "raw": result.stdout,
            }

        # Parse JSON output
        stdout = result.stdout.strip()
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            # Raw text fallback
            return {"result": stdout, "usage": {}, "raw": stdout}

    @staticmethod
    def _extract_text(data: Dict[str, Any]) -> str:
        """Extract the assistant text from a parsed claude -p JSON response.

        The ``claude -p --output-format json`` response has the shape:
          { "type": "result", "result": "<text>", "is_error": false, ... }
        """
        if "error" in data:
            return ""
        # Primary field from claude -p --output-format json
        result_text = data.get("result")
        if result_text is not None:
            return str(result_text)
        # Fallback: raw text (non-JSON response that was wrapped)
        return data.get("raw", "")

    @staticmethod
    def _check_is_error(data: Dict[str, Any]) -> Optional[str]:
        """Return error string if the CLI reported is_error, else None."""
        if data.get("is_error"):
            return data.get("result") or "claude reported is_error=true"
        return None

    @staticmethod
    def _extract_tool_use(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return the first tool_use block if present, else None.

        This is kept for compatibility; in practice the Python-driven M3
        broker handles tool loops without requiring the CLI to emit tool_use
        blocks — the broker drives lookups directly.
        """
        for block in data.get("content", []):
            if block.get("type") == "tool_use":
                return block
        return None

    @staticmethod
    def _token_count(data: Dict[str, Any]) -> tuple:
        """Return (input_tokens, output_tokens) from CLI usage dict."""
        usage = data.get("usage", {})
        inp = (
            usage.get("input_tokens")
            or usage.get("prompt_tokens")
            or 0
        )
        out = (
            usage.get("output_tokens")
            or usage.get("completion_tokens")
            or 0
        )
        return int(inp), int(out)

    def _transcript_path(self, question_id: Optional[str] = None) -> Optional[str]:
        if not self._transcript_dir:
            return None
        os.makedirs(self._transcript_dir, exist_ok=True)
        ts = int(time.time())
        name = f"{question_id or 'ask'}_{ts}.jsonl"
        return os.path.join(self._transcript_dir, name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ask(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_turns: int = 1,
        tool_broker: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> AskResult:
        transcript_lines: List[Dict[str, Any]] = []
        tool_calls_log: List[ToolCall] = []
        total_input = 0
        total_output = 0
        total_injected = 0
        turn_num = 0
        current_user = user_prompt
        final_text = ""
        error: Optional[str] = None

        for turn_num in range(1, max_turns + 1):
            # Measure injected tokens for this turn
            injected_this_turn = _count_injected_tokens(system_prompt, current_user)
            total_injected += injected_this_turn

            data = self._run_turn(system_prompt, current_user)
            transcript_lines.append({"turn": turn_num, "response": data})

            if "error" in data:
                error = data["error"]
                break

            # Check CLI-level error flag
            cli_error = self._check_is_error(data)
            if cli_error:
                error = cli_error
                break

            inp, out = self._token_count(data)
            total_input += inp
            total_output += out

            # Check for tool use (M3 multi-turn via Python broker)
            tool_block = self._extract_tool_use(data) if tool_broker else None
            if tool_block:
                tool_name = tool_block.get("name", "")
                tool_args = tool_block.get("input", {})
                try:
                    tool_result = tool_broker(tool_name, tool_args)
                except Exception as exc:
                    tool_result = {"error": str(exc)}

                tc = ToolCall(
                    turn=turn_num,
                    name=tool_name,
                    arguments=tool_args,
                    result=tool_result,
                )
                tool_calls_log.append(tc)
                transcript_lines.append({"turn": turn_num, "tool_result": tool_result})

                # Feed result back as next user message
                current_user = json.dumps(
                    {"tool_result": tool_result}, ensure_ascii=False
                )
                continue

            # No tool use — final response
            final_text = self._extract_text(data)
            break

        # Write transcript
        t_path: Optional[str] = None
        if self._transcript_dir and transcript_lines:
            t_path = self._transcript_path()
            if t_path:
                with open(t_path, "w", encoding="utf-8") as fh:
                    for line in transcript_lines:
                        fh.write(json.dumps(line, ensure_ascii=False) + "\n")

        if error:
            return AskResult.from_error(error, driver_name=self.name)

        return AskResult(
            response_text=final_text,
            input_tokens=total_input,
            output_tokens=total_output,
            injected_tokens=total_injected,
            turns=turn_num,
            transcript_path=t_path,
            tool_calls=tool_calls_log,
            driver_name=self.name,
        )
