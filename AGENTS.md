# AGENTS.md — cog-workbench contributor instructions

Read the suite guide linked from README.md for project context.
This file is the repo-local contract for any agent or human editing here.

## What this repo is

The ACTIVE experiment: a fork of the earlier reference client (cog-client
v0, an internal package that is not distributed), with the portable
contract's gaps filled *by proposal*. That client and the original frozen
Cogs it inspected are not modified; this is where new ideas run. Every design change MUST be recorded in `DECISIONS.md`
with alternatives considered and tradeoffs — that file is a meeting input,
not documentation-after-the-fact.

## Commands

- Serve: `pixi run serve -- --path <path-to-a-cog-package>`
  (port 8071; or plain `python3 src/cog_workbench_web.py` — the server needs
  only python + pyyaml)
- Test: `python3 -m unittest discover -s tests` — 59 tests, model-free,
  use the Python version declared in pixi.toml. Playwright drives live
  E2E in cloud sessions only.

## Invariants — do not regress

1. **Naming:** never handler/runner/harness for anything client-side
   (Travis vocabulary, ratified). This is a *reference client* /
   *invocation environment*.
2. **Execution guardrail:** the server runs only operations derived from
   the loaded package's own declarations (interfaces, conventional tasks,
   dependency default tasks) and derivations declared in its input schema.
   No free-form commands, ever. Derivation values are argv data (tokens on
   the pixi tier, shlex-quoted on the fallback tier).
3. **Closed vocabulary:** `x-cog-param` types are interpreted from a fixed
   set; a Cog can never name a command to run for UI purposes. Unknown
   version or type must degrade to a plain labeled input.
4. **Frozen deps + overlay rule:** never edit the original frozen Cogs or
   the reference client (internal packages, not distributed). Declarations
   the frozen Cogs "should" have live in
   `overlays/<cog-id with / → -->/input-schema.json`; a real manifest
   `context.input_schema` declaration always wins over an overlay.
5. **Portability:** no new runtime dependencies. Keep `toml_compat`
   (tomllib fallback for <3.11) and scrub `PIXI_*` from child-process
   environments (`proc_manager._child_env`).
6. **Everything journaled:** process start/stop/exit, invoke, chat turns,
   derivations → `var/activity.jsonl` (gitignored).
7. **Satisfiers of one capability are alternatives** — bring-up needs any
   one serving, tried in declared order.
8. **Meeting-owned gaps stay open:** the response envelope is discovered
   heuristically and HTTP-200-with-problems has no pass rule *on purpose*
   (DECISIONS §4). Do not "fix" these client-side.

## Design stance (from Trent, recorded in DECISIONS §6–7)

Ease of use is the product. Order-of-operations belongs in the tool
(bring-up sequence, stale-binding restart). For input mistakes the priority
is: smart defaults first, self-correction second (e.g. reversed git-range
swap), labels last — a design that needs the label read is the bug.

## Housekeeping

- `var/` and `.pixi/` are gitignored; clean `__pycache__` before commits.
- Generate lockfiles with Pixi on a supported platform with access to the
  declared channels. Preserve every declared platform and verify `pixi install --locked`.
- Commit using your own configured Git identity. Attribute collaborators
  accurately; do not impersonate another contributor.
