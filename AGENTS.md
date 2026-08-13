# AGENTS.md — cog-workbench contributor instructions

Read `../CLAUDE.md` (coglab root) for workstream context and vocabulary.
This file is the repo-local contract for any agent or human editing here.

## What this repo is

The ACTIVE experiment: cog-client v0 forked, with the portable contract's
gaps filled *by proposal*. cog-client and cog-forge are frozen; this is
where new ideas run. Every design change MUST be recorded in `DECISIONS.md`
with alternatives considered and tradeoffs — that file is a meeting input,
not documentation-after-the-fact.

## Commands

- Serve: `pixi run serve -- --path ../cog-forge/cog-release-notes`
  (port 8071; or plain `python3 src/cog_workbench_web.py` — the server needs
  only python + pyyaml)
- Test: `python3 -m unittest discover -s tests` — 41 tests, model-free,
  must pass on Python 3.10 (the device VM floor). Playwright drives live
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
4. **Frozen deps + overlay rule:** never edit `../cog-forge` or
   `../cog-client`. Declarations the frozen Cogs "should" have live in
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
- pixi lockfiles are regenerated only on Trent's Mac (conda-forge is
  403-blocked in sandboxes and the device VM).
- Commits: author Trent Oliphant <trentoliphant@gmail.com>; keep the
  Claude co-author/session trailers convention used in `git log`.
