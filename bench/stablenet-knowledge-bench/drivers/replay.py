"""replay.py — deterministic replay driver for offline CI.

The replay driver looks up canned responses keyed by the SHA-256 of the
``(system_prompt, user_prompt)`` tuple.  This makes tests fully deterministic
and offline — no live AI calls needed.

Fixture directory layout
------------------------
    <replay_dir>/
        <hex_sha256[:16]>.json   # one fixture file per (system_prompt, user_prompt) pair
        index.json               # optional: maps prompt_sha -> fixture filename

Fixture JSON schema (single-turn)
----------------------------------
    {
      "prompt_sha": "<full sha256 hex>",
      "response_text": "<canned response>",
      "input_tokens": 1234,
      "output_tokens": 56,
      "turns": 1,
      "tool_calls": [],
      "driver_name": "replay"
    }

If no fixture is found for the prompt, the driver returns a synthetic
"REPLAY_MISS" error result so tests fail loudly.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Callable, Dict, List, Optional

from .base import AskResult, Driver, ToolCall


class ReplayDriver(Driver):
    """Offline replay driver that returns canned responses from fixture files.

    Parameters
    ----------
    replay_dir : str
        Path to the directory containing fixture JSON files.
    strict : bool
        If True (default), a missing fixture causes an error AskResult.
        If False, returns a generic placeholder response (useful for smoke tests).
    """

    name = "replay"

    def __init__(self, replay_dir: str, strict: bool = True) -> None:
        if not os.path.isdir(replay_dir):
            raise ValueError(f"ReplayDriver: replay_dir does not exist: {replay_dir}")
        self._replay_dir = replay_dir
        self._strict = strict
        self._index: Optional[Dict[str, str]] = self._load_index()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_index(self) -> Optional[Dict[str, str]]:
        idx_path = os.path.join(self._replay_dir, "index.json")
        if os.path.isfile(idx_path):
            with open(idx_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        return None

    @staticmethod
    def prompt_sha(system_prompt: str, user_prompt: str) -> str:
        """Compute the SHA-256 key for a (system_prompt, user_prompt) pair."""
        payload = json.dumps([system_prompt, user_prompt], ensure_ascii=False, sort_keys=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _find_fixture(self, sha: str) -> Optional[str]:
        """Return the path to a fixture file for the given sha, or None."""
        # Check index first
        if self._index is not None:
            fname = self._index.get(sha)
            if fname:
                path = os.path.join(self._replay_dir, fname)
                if os.path.isfile(path):
                    return path

        # Fallback: <first 16 chars of sha>.json or <full sha>.json
        for candidate in (f"{sha[:16]}.json", f"{sha}.json"):
            path = os.path.join(self._replay_dir, candidate)
            if os.path.isfile(path):
                return path

        return None

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
        sha = self.prompt_sha(system_prompt, user_prompt)
        fixture_path = self._find_fixture(sha)

        if fixture_path is None:
            if not self._strict:
                # Return a generic placeholder
                return AskResult(
                    response_text=(
                        '{"answer": "REPLAY_PLACEHOLDER", "citations": []}'
                    ),
                    input_tokens=100,
                    output_tokens=20,
                    turns=1,
                    driver_name=self.name,
                )
            return AskResult.from_error(
                f"REPLAY_MISS: no fixture for prompt_sha={sha[:16]}… "
                f"(replay_dir={self._replay_dir})",
                driver_name=self.name,
            )

        with open(fixture_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        tool_calls: List[ToolCall] = [
            ToolCall(
                turn=tc.get("turn", 1),
                name=tc.get("name", ""),
                arguments=tc.get("arguments", {}),
                result=tc.get("result"),
            )
            for tc in data.get("tool_calls", [])
        ]

        return AskResult(
            response_text=data.get("response_text", ""),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            turns=data.get("turns", 1),
            transcript_path=fixture_path,
            tool_calls=tool_calls,
            error=data.get("error"),
            driver_name=self.name,
        )

    # ------------------------------------------------------------------
    # Fixture creation helper (used by tests to build fixtures)
    # ------------------------------------------------------------------

    @staticmethod
    def write_fixture(
        replay_dir: str,
        system_prompt: str,
        user_prompt: str,
        response_text: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        turns: int = 1,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Write a fixture file to replay_dir and return the file path.

        Also updates (or creates) the index.json.
        """
        os.makedirs(replay_dir, exist_ok=True)
        sha = ReplayDriver.prompt_sha(system_prompt, user_prompt)
        fname = f"{sha[:16]}.json"
        fpath = os.path.join(replay_dir, fname)

        fixture = {
            "prompt_sha": sha,
            "response_text": response_text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "turns": turns,
            "tool_calls": tool_calls or [],
            "driver_name": "replay",
        }
        with open(fpath, "w", encoding="utf-8") as fh:
            json.dump(fixture, fh, indent=2, ensure_ascii=False)

        # Update index
        idx_path = os.path.join(replay_dir, "index.json")
        index: Dict[str, str] = {}
        if os.path.isfile(idx_path):
            with open(idx_path, "r", encoding="utf-8") as fh:
                index = json.load(fh)
        index[sha] = fname
        with open(idx_path, "w", encoding="utf-8") as fh:
            json.dump(index, fh, indent=2, ensure_ascii=False)

        return fpath
