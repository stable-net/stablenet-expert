# p5-cleanup-scope — does the stream-6 P5 patch stop killing the developer's node?

P5 (see `docs/coding-agent-overlay-improvements-and-eval-2026-06-22.md`) fixes the
evaluator §7.6 cleanup. The pre-P5 cleanup ran:

```
for pid in $(pgrep -f 'gstable'); do kill -TERM $pid; done
```

which kills **every** matching process — including a developer's unrelated local
`gstable` node, and even the shell running the loop (its own argv contains the
pattern). P5 scopes the kill to processes this run actually started: snapshot the
matching PIDs **before** `chainbench_start()` (§7.3), then in §7.6 terminate only
the PIDs that match AND are absent from that snapshot AND are not `$$`/`$PPID`.

## Files

| file | role |
|---|---|
| `cleanup_scoped.sh` | reference scoped cleanup: `snapshot <pattern>` / `cleanup <pattern> <prepids-file>` |
| `verify.sh` | binary safety test with real (harmless `sleep`) dummies |

## Run

```
bash bench/p5-cleanup-scope/verify.sh      # exit 0 only if scoped spares foreign + kills ours
```

The test, with a unique per-run marker so it only ever touches its own dummies:
1. starts a "foreign" dummy (the developer's pre-existing instance),
2. snapshots,
3. starts "ours" (after the snapshot),
4. runs the scoped cleanup, and asserts **foreign survives** while **ours is killed**,
5. then shows the pre-P5 naive `pkill -f <pattern>` kills the foreign one too — the bug.

## Result (2026-06-22)

```
PASS: foreign <pid> survived scoped cleanup
PASS: ours <pid> terminated by scoped cleanup
confirmed: naive pkill killed foreign <pid> (the pre-P5 bug)
P5 cleanup-scope: PASS
```

## Note

This is the one overlay item whose artifact is inherently process-level, so the
harness is a real-process integration test rather than a pure-logic corpus (unlike
`bench/p0-mutants/` and `bench/p2-cks-fault/`). `cleanup_scoped.sh` is the reference
the evaluator §7.6 prose mirrors; keep them in sync.
