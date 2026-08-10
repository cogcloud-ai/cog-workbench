# DECISIONS — how each gap was filled, and what was traded away

cog-client v0 stopped exactly where the portable contract stopped, and its
GAPS.md lists the nine places it had to guess. This workbench is the
experiment Trent asked for: *decide what would work, build it, and write the
decisions down.* Each section below names the gap, the chosen design, the
alternatives considered, and the tradeoffs. Everything here is a **proposal
wearing running code** — none of it is ratified, and the meeting can overrule
any of it cheaply because each mechanism is isolated.

## 0. Ground rule: the frozen artifacts stay frozen

The forge Cogs passed an engineering-gates verdict and cog-client v0 is the
"what works under today's constraints" demo. Neither is modified. New
declarations the experiment needs (input schemas) ship as **overlays** in this
repo (`overlays/<cog-id>/input-schema.json`), and the client prefers a real
in-manifest declaration (`context.input_schema`) when one exists.

*Tradeoff:* overlays weaken the principle that the Cog declares everything —
a sidecar is exactly the kind of out-of-band knowledge a generic client
shouldn't need. Accepted deliberately: the overlay file IS the text the
manifest would gain, so the proposal stays concrete while the frozen packages
stay untouched. If the proposal is ratified, each overlay moves into its Cog
and the overlay mechanism is deleted.

## 1. Input schemas → generated forms (GAPS #2)

**Decision:** a Cog declares `context.input_schema` pointing at a JSON Schema
for its task bundle. The workbench generates the form from it: enums become
dropdowns, booleans checkboxes, annotated strings become textareas, and a small
extension vocabulary `x-cog-input` covers what JSON Schema can't say about UI:

- `{"source": "file", "encoding": "text"}` on a string property → a file
  picker whose *content* fills the field (read client-side with FileReader —
  no upload endpoint, no server filesystem browsing);
- `{"builder": "file-items", "file_field": "content", "id_prefix": "ev-"}` on
  an array of objects → a row builder: pick a file, get an item with an
  editable id, a type dropdown (from the item schema's enum), and the file's
  content — this is how the CI analyst's evidence bundle becomes three file
  picks instead of hand-built JSON;
- `{"builder": "json"}` → a JSON sub-editor for structures too complex to
  form-ify (release-notes commits, which are git-derived anyway);
- `{"widget": "textarea"}` → rendering hint.

**Alternatives considered:** (a) full recursive form generation for arbitrary
schemas — rejected: deep nested editors are a project in themselves and the
80% case is flat-object-plus-one-collection; the JSON sub-editor is the honest
escape hatch. (b) Server-side file browsing so the form can reference paths —
rejected: a loopback server exposing filesystem browsing is a worse security
posture than the browser's own file picker, and content-in-bundle matches how
the Cogs' own `make_bundle` helpers already work. (c) Deriving forms from the
`examples/` alone — that's v0's fallback and it can't know types, enums, or
required fields.

**Tradeoff:** `x-cog-input` mixes UI concern into a data contract. Kept
minimal (4 keys) and namespaced so a non-UI consumer can ignore it entirely.

## 2. Runnable operations (the "buttons actually run things" ask)

**Decision:** the workbench executes a Cog's tasks server-side, as managed
processes with captured logs, start/stop, and status — but ONLY tasks that are
*derived from declarations*: interface tasks, the conventional binding tasks
(`resolve`, `use`, `check`, `eval`, `test`, `bundle`) present in the Cog's own
pixi.toml, and — the piece that makes chat actually work — **dependency
operations**: each locally-sourced declared satisfier becomes a "start
dependency" button wired to *that* Cog's default interface task. The full
chain (start model → resolve → start web-api → invoke/chat) is four buttons.

Command resolution is two-tier, same rule as cog-forge's checks: if the Cog's
locked pixi env executes on this machine → `pixi run --frozen <task>`;
otherwise the task string is read from pixi.toml and run on the system
interpreter, and the UI labels which tier ran.

**Why v0 refused this:** running someone's tasks is authority. The resolution
isn't to pretend otherwise — it's to notice that holding exactly this
authority is what *distinguishes* an invocation environment from an inspector.
The §6.6 "surround" Collab would run IS this. Guardrails: no free-form
commands ever (the server re-derives the operation list and refuses anything
not on it), one instance per (cog, task), process-group kill on stop, and
every start/stop/exit journaled.

**Alternatives considered:** (a) whitelisting exact command strings in the
manifest (`run:` per interface) — cleaner in theory, but it duplicates
pixi.toml and drifts; tasks-by-name keeps pixi.toml the single source.
(b) Only ever running through pixi — correct-est, but makes the workbench
unusable anywhere the locked env can't materialize (like this sandbox), and
the fallback is honest about itself. (c) A `dry_run` preview of the resolved
command — cheap, worth adding later.

**Tradeoff:** a loopback server that starts processes is a bigger attack
surface than one that only reads. Accepted for a loopback-only, no-auth
development tool; a deployed Collab would put its real authorization layer
exactly here, which is the point of demonstrating the seam.

## 3. Chat that works (GAPS #3 + the practical failure)

**Decision:** the chat surface itself is v0's (client-held thread, stateless
turns) — what was broken wasn't the chat, it was that nothing was serving.
Three fixes: the Operations tab can start the model (or the whole stack) with
buttons; the chat tab *pre-flight probes* its endpoint and, when it's down,
says so and deep-links to Operations instead of failing silently; and turn
failures render inline in the thread with the same pointer. Conversability is
still *inferred* from `kind: openai-compatible` — the `io.accepts`
vocabulary remains the meeting's to ratify, and the inference is still
labeled as a gap.

**Not done:** streaming (GAPS #8). llama-server supports SSE and the proxy
could pass chunks through, but it roughly doubles the server's complexity for
a demo property. Deferred with a note; a `streaming: true` interface flag is
the manifest-side half whenever wanted.

## 4. Envelope + pass/fail (GAPS #1, #4)

**Decision:** unchanged from v0 — the payload key is still discovered
heuristically and the banner still says so, *on purpose*. Fixing this
properly means changing what the Cogs emit, and the Cogs are frozen; fixing it
client-side only would just bake the guess in deeper. The workbench adds one
practical rule on top: results render in three visual states (ok / ok-with-
problems / error) so "passed with integrity problems" is at least legible to a
human even though no machine rule defines it. This is the one gap that only
the meeting can close, and the workbench keeps demonstrating that on every
invocation.

## 5. Activity journal (the minimal §6.6 surround)

**Decision:** every operation start/stop/exit, invocation, and chat turn is
appended to `var/activity.jsonl` (gitignored) with timestamp, cog, outcome,
problem count, and model identity, and rendered in an Activity tab. This is
deliberately the *smallest honest version* of the audit Track — enough to show
where run records accumulate in an invocation environment, without inventing
a record schema the spec hasn't ratified. The full per-run binding record
already exists inside each invocation result; the journal indexes, it doesn't
duplicate.

## 6. Order of operations is the tool's job (added after first real use)

**The failure that motivated this:** first real run on a user's machine
produced `identity mismatch — requested 'local'`. Cause: web-api was started
before `resolve`, so the service loaded the built-in default binding at
process start and never saw the record resolve later wrote. Everything worked
as designed — and the design still put a sequencing burden on the human. If
Cogs demand that users know start-order and restart semantics, they won't get
used; the whole point is to make running them easy.

**Decision, two layers:**

1. *Staleness is detected, not remembered.* Every process snapshot carries its
   `started_ts`; the server reports `model.json`'s mtime alongside. A running
   service of the loaded Cog whose binding record is newer than its start gets
   an inline warning and a **Restart** button. No new state — just comparing
   two timestamps that already existed.
2. *The sequence itself is a button.* **"Bring up the stack"** runs the whole
   order: start each declared dependency → wait for ITS health surfaces →
   run `resolve` → wait for exit 0 → start the Cog's service (restarting it
   if it predates the fresh binding) → wait for ITS health. Progress is
   narrated inline; any failure stops the sequence and points at the logs.

**Alternatives considered:** (a) hot-reload the binding record per request in
the Cogs themselves — the correct long-term fix, but the Cogs are frozen, and
read-once-at-start is also a defensible §6.7 stance (a running service's
binding should not drift silently mid-flight; an explicit restart is an
auditable event). (b) Server-side orchestration endpoint — rejected for now:
client-side sequencing reuses the existing (guardrailed) endpoints unchanged,
keeps progress visible, and adds zero new server authority. (c) Auto-running
resolve at web-api start — too magical: resolve writes installation state,
and writing state as a side effect of starting a viewer crosses a line the
spec should decide, not this tool.

**Tradeoff:** the bring-up sequence hard-codes one topology (deps → resolve →
serve). It is derived from declarations, but the *ordering rule* is the
workbench's opinion. That's exactly the kind of knowledge Collab's invocation
environment will need to own — another concrete input for the meeting: should
a Cog declare its own bring-up order, or is that always the environment's?

### Also in the ease-of-use bucket: opening Cogs without typing paths

Typing an absolute path into a box is the same adoption killer as knowing the
start order. The **Browse…** dialog lists directories and runs a bounded scan
(3 levels, hidden/heavy dirs skipped, Cogs are leaves) for `cog.yaml`
packages, so opening a Cog is: Browse → click it.

This does NOT reverse §1's rejection of server-side file browsing. That
rejection was about pulling file *content* into invoke payloads — content
selection stays user-mediated through the browser's own picker. The open
dialog returns directory *metadata* (names + cog.yaml headers), which is the
same authority `/api/package?path=` already had. *Tradeoff:* the loopback
server now enumerates directory names on request; accepted for a loopback
dev tool. The real fix at product level is an installed-Cog index (the Nebi
desktop surface Trent floated) — this dialog is the minimal stand-in that
proves what it needs: package discovery wants to be a service the invocation
environment provides, not knowledge in the user's head.

## 7. What stayed in cog-client v0

The inspector, affordance derivation, generic envelope interpretation, and
health probes came across unchanged (v0 remains the demo of "today's
constraints only"). The CLI is unchanged except that it now lives beside the
workbench server; the buttons are the new surface, not a replacement for it.

## Scorecard against GAPS.md

| Gap | Status here |
|---|---|
| #1 envelope | **Demonstrated, not filled** — only ratification can fill it |
| #2 input schema | **Filled by proposal** (`context.input_schema` + `x-cog-input`, overlays for frozen Cogs) |
| #3 io vocabulary | **Worked around** (kind-inference), still labeled a gap |
| #4 problems-on-200 | **Made legible** (three-state rendering), rule still unratified |
| #5 install-time address / binding record | **Operable** — resolve runs via button, binding renders as installation state |
| #6 credential presence | Unchanged (reference works; presence unknowable) |
| #7 fixed ports | Unchanged (dependency ops make collisions visible at least) |
| #8 streaming | **Deferred**, documented |
| #9 health conventions | Unchanged conventions, now attached to live process state |
