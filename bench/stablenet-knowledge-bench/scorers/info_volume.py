"""info_volume.py — information volume scorer.

This metric measures how many tokens of *injected context* the AI was given
to answer the question for each context-provision method.

IMPORTANT: the ``injected_tokens`` value (not ``input_tokens``) is used
here.  ``input_tokens`` from the Claude CLI includes ~20 k of Claude Code's
own system-prompt overhead that is constant across all methods and would
mask M1-vs-M4 differences.  ``injected_tokens`` is measured as
``len(system_prompt + user_prompt) // 4`` by the driver — only the context
the harness constructed.  For M3 multi-turn it is the sum across turns.

A lower injected_tokens value for the same or better correctness/location
score indicates the CKG is providing more targeted context.
"""

from __future__ import annotations


def score_info_volume(injected_tokens: int) -> int:
    """Return the information volume metric.

    Parameters
    ----------
    injected_tokens : int
        The ``injected_tokens`` field from AskResult — the harness-injected
        context size (system_prompt + user_prompt, len // 4).  May be 0 if
        the driver did not measure it (treated as unknown).

    Returns
    -------
    int
        The raw injected_tokens value.  Never raises; negative values
        clamped to 0.
    """
    return max(0, int(injected_tokens))
