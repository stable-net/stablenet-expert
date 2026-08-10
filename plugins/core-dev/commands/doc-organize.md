---
description: Consolidate docs/ under a 3-tier discipline. Code plus git decide conflicts; vision is preserved; supersede rather than delete. Plan first, apply after approval.
argument-hint: "[a path or topic to organize]   (omit for all of docs/)"
---

# /core-dev:doc-organize

Consolidate and organize a repository's documentation under a **3-tier
discipline**, so design evolution stops (a) forcing repeated "which design is
right?" reviews and (b) eroding the project's purpose/vision during cleanup.

This command is **self-contained** — it does not require the host repo to
already have a governance setup. Scope hint (optional): $ARGUMENTS
(empty → review all of `docs/`; a path/topic → restrict to it).

## The 3-tier model

- **Tier 1 — `docs/VISION.md`** (purpose/vision): why the project exists.
  Append-mostly. **Read-only input to cleanups, never a target.**
- **Tier 2 — design/specs incl. `docs/adr/`**: how/why something was decided.
  One decision = one ADR. **Supersede, don't delete.**
- **Tier 3 — state/status/remaining-work**: dated, disposable, regenerable from
  code + git.

## Rules — apply strictly

1. **Ground truth = code + git.** For any claim about *current* state, verify
   against the tree and `git log` / `git -L`, cite `file:line`, and report which
   doc is stale. Never trust doc prose over code. If you cannot confirm
   something from code, mark it "unverified" — do not guess.
2. **Tier 1 is read-only input.** `docs/VISION.md` must NOT be deleted or
   shrunk. If purpose/vision prose is scattered in other docs, MOVE it into
   VISION.md — never drop it.
3. **Decisions: supersede, don't delete.** A changed decision becomes a NEW ADR
   with the old one marked `Superseded by ADR-NNNN` (one-line reason). Old
   design docs move to `docs/archive/` with a "superseded by X" note.
4. **Single source of truth for volatile facts.** Counts, versions, and other
   values that live in code (schema version, type counts, tool lists) belong in
   ONE doc that points at the code; other docs link to it instead of restating
   the numbers, so a bump updates one place.
5. **Don't proliferate docs.** Prefer updating an existing Tier 2/3 doc over a
   new `.md`. New file only for a genuinely new decision (→ ADR) or a new dated
   status snapshot.
6. **Keep the index honest.** Every add/move/supersede updates `docs/DOC-MAP.md`
   (and the ADR index) in the same change.

## Procedure

### Step 0 — Bootstrap check (only if missing)
If `docs/VISION.md`, `docs/DOC-MAP.md`, or `docs/adr/` do not exist, the repo
has no 3-tier scaffolding yet. Offer to create it first:
- `docs/VISION.md` — distil the durable purpose from README / overview docs
  (do NOT invent; extract and cite).
- `docs/DOC-MAP.md` — tier-classified index of every existing doc.
- `docs/adr/README.md` — ADR template + index.
Get approval, create them, then continue. (If the user declines, still apply
the rules below to whatever docs exist.)

### Step 1 — Discover & verify
Identify the docs in scope. For each pair covering the same topic, detect
conflicts and resolve each against code + git.

### Step 2 — Plan first (do NOT mutate yet)
Present a table:

| Doc | Tier | Action (keep / update / merge-into-X / move-to-archive / supersede-by-ADR) | Reason (+ code evidence for staleness) |

List separately: (a) any vision/purpose prose found outside VISION.md that must
be preserved, (b) any doc-vs-code conflicts with the verified verdict.

### Step 3 — Stop and ask for approval
Do not perform destructive moves/merges/deletes until the user approves.

### Step 4 — Apply
Use `git mv` for moves (preserve history). Then update `docs/DOC-MAP.md` and the
ADR index.

### Step 5 — Report
What changed, plus anything still needing human judgment.

Begin at Step 0.
