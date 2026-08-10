# cog-workbench

The gap-filled fork of `cog-client`: same inspector, but the client now holds
the authority an invocation environment actually has. Point it at a Cog and it
renders — **and runs** — what the package declares:

- **Operations with buttons.** Every declared interface task, the Cog's own
  binding machinery (`resolve`/`use`/`check`/`eval`), and each declared
  dependency become Start/Stop/Run buttons with live logs. The chain that
  makes everything else work — start the model Cog, resolve, start the
  web-api — is four clicks, not a terminal tour.
- **Schema-driven forms with file pickers.** A proposed `context.input_schema`
  contract (JSON Schema + a tiny `x-cog-input` vocabulary) generates the
  invoke form: dropdowns from enums, file pickers that fill evidence items
  with file content, JSON sub-editors for the genuinely complex parts.
  Shipped as overlays for the frozen forge Cogs.
- **Chat that works.** Same client-held-thread surface, plus a pre-flight
  probe that tells you the model isn't serving and takes you to the button
  that starts it.
- **An activity journal** — the minimal §6.6 audit surround: every start,
  stop, invocation, and chat turn.

`cog-client` stays as the demo of *today's* portable contract; this repo is
the experiment in what the contract should become. Every design call and its
tradeoffs are written down in [`DECISIONS.md`](DECISIONS.md).

## Run it

```bash
pixi install
pixi run serve -- --path ../cog-forge/cog-ci-failure-analyst
# open http://127.0.0.1:8071
```

Then, in the UI: **Operations → ⚡ Bring up the stack** — one button that
starts the dependency, waits for it, resolves, and (re)starts the service in
the right order, narrating as it goes. (The individual Start/Run/Stop buttons
are still there, and a service running on a binding older than `model.json`
gets an inline warning and a Restart button.) Then use **Run** (pick a log
file, pick the workflow) or **Chat**. CLI (`show`/`ask`/`chat`/`health`) is
unchanged from cog-client.

Loopback only, no auth, and the server will only run tasks derived from the
package's own declarations — never a free-form command. `pixi run test` runs
the 33-test model-free suite. The server itself needs only Python + PyYAML —
pixi.toml parsing degrades to an honest built-in fallback on interpreters
older than 3.11 (`src/toml_compat.py`).

## Where things stand

| Piece | Contract status |
|---|---|
| `context.input_schema` + `x-cog-input` | **Proposed here**; overlays stand in for the frozen Cogs |
| Runnable operations semantics | **Proposed here** (declared-tasks-only rule) |
| Response envelope / pass-fail rule | **Still the meeting's** — the workbench demonstrates the gap on every invocation |
| `io` conversability vocabulary | **Still the meeting's** — chat-shape remains inferred and labeled |
| Streaming | Deferred (`DECISIONS.md` §3) |
