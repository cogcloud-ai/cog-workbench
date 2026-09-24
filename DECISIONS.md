# DECISIONS — how each gap was filled, and what was traded away

The earlier reference client (cog-client v0, an internal package that is not
distributed) stopped exactly where the portable contract stopped, and its gap
record lists the nine places it had to guess. This workbench is the
experiment Trent asked for: *decide what would work, build it, and write the
decisions down.* Each section below names the gap, the chosen design, the
alternatives considered, and the tradeoffs. Everything here is a **proposal
wearing running code** — none of it is ratified, and the meeting can overrule
any of it cheaply because each mechanism is isolated.

## 0. Ground rule: the frozen artifacts stay frozen

The original frozen Cogs (the "forge" Cogs, internal packages that are not
distributed) passed an engineering-gates verdict and cog-client v0 is the
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

Command resolution is two-tier, the same rule the frozen Cogs' own check
scripts use: if the Cog's
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

## 7. x-cog-param: parameter semantics + declared derivation (prototype)

The full proposal is an internal design note (not distributed, drafted for
the Monday meeting); this section records what runs here and the calls made.

**The gap:** the schema says a value's *shape* (string), not what it *is*
(a git ref of the repo named in another field). Generic clients therefore
render exams: text boxes for refs the user must already know.

**Decision:** a second namespaced layer inside the input schema —
`x-cog-param` v1 — with (a) a CLOSED vocabulary of semantic types
(`local-path`, `git-repo`, `git-ref` with `repo_from`, `github-repo`) and
(b) **declared derivation**: a field (or the whole form, `fills: "$"`) can
declare itself producible by one of the Cog's own tasks plus an argv
template. The workbench maps types to capabilities it trusts: a repo picker
(the Browse dialog in git mode), a ref dropdown (ONE fixed read-only
`git for-each-ref` argv — a client capability, never a Cog-supplied
command), and a Build button that runs the declared `bundle` task and fills
the form from its JSON output.

**Guardrails, same shape as runnable operations:** the derive id must come
from the package's own (schema or overlay) declaration; the task must exist
in its pixi.toml; user values are argv DATA (tokens on the pixi tier,
shlex-quoted on the fallback tier); `{output}` is a server-chosen temp file;
every derivation is journaled. Closed vocabulary is the line that holds:
the moment a Cog can say "run this to populate my dropdown," free-form
execution is back.

**Degradation:** unknown vocabulary version → no panels; unknown semantic
type → labeled text box; extension absent → exactly yesterday's form. That
property is why this can be a Collab-side extension instead of core spec.

**Auth stance:** browser GitHub cookies never reach a local client (correct
CORS/cookie scoping, not a bug to fix). Local clones need no auth; remote
private repos are a client capability (`gh` CLI, `api_key_env`-style
references) — the extension never carries credentials.

**Assumption-proofing (added after second real use):** the first real user
picked the newest ref as the range start without reading the "(exclusive)"
label — because nobody reads labels, and a design that needs them read is
the bug. Three responses, in order of importance: *smart defaults* (a
`prefer: "latest-tag"` hint in the vocabulary — release notes usually start
at the last release, so the common case is now zero picks); *a reversed-range
guard* (both ends carry creatordates from the ref listing; if "from" is
newer than "to" the client swaps them and says so, rather than failing);
and only then *better labels* ("notes cover everything AFTER… / …up to").
Labels are the last line of defense, not the first.

**Tradeoff:** the argv template puts command-line syntax into a data file —
mild duplication of the task's argparse surface, accepted because it is what
makes execution *declarable* rather than free-form. cog-smith can draft
these blocks mechanically from `--help` output (nf-core's `schema build`
precedent).

## 8. What stayed in cog-client v0

The inspector, affordance derivation, generic envelope interpretation, and
health probes came across unchanged (v0 remains the demo of "today's
constraints only"). The CLI is unchanged except that it now lives beside the
workbench server; the buttons are the new surface, not a replacement for it.

## Future direction: cog-workbench tool suite

Recorded 2026-09-07: Trent prefers retaining **cog-workbench** as the name
for the broader collection of tools for building, evaluating, testing and
working with Cogs. This is a direction for future development, not a claim
that these workflows are already integrated.

The **dynamic selector/binder** is a component within that suite. It discovers
eligible satisfiers, selects compatible Context / Harness / Model combinations,
and coordinates qualification and host admission into explicit bindings.
Selection does not itself grant authority; admission remains a host decision.
Invocation, building, testing and evaluation can consume those bindings through
shared contracts. The selector/binder is client-side tooling, distinct from
the Harness-only Cog supplying the interaction machinery.

Workbench can coordinate specialized tools and Cogs: cog-author for authoring,
cog-smith for final packaging and package checks, and cog-build-evaluator for
evaluation planning and evidence review. Their existing responsibilities remain
useful component boundaries as the suite grows.

**Alternatives and tradeoffs:** retain the established workbench name rather
than rename it around binding or create a separate umbrella product. Keep the
selector/binder a distinct component so multiple workflows can use it without
coupling selection policy to the UI. Its final name, API and repository boundary
remain open; a suite does not require every tool to live in one repository.

## Future tooling: dynamic Context / Harness / Model composition

Recorded 2026-09-07 at Trent's request. **Backlog item only; implementation
is not started or authorized by this record.**

Workbench should support assembling separately selected Context, Harness-only
and Model Cogs. Its existing dependency → resolve → serve sequence and model.json
display do not implement independent harness binding or three-part composition.

The future capability should:

- Discover the context Cog's model and harness requirements and the available
  providers' configuration and credential-reference contracts.
- Qualify and admit a model binding, then a compatible Harness-only binding
  referencing that exact model revision; preserve Model versus Model+Harness
  distinctions rather than silently substituting one for another.
- Supply the context Cog's permitted context and packaged contract checks to
  the selected harness, honoring memory, tool grants and approval requirements.
- Invoke the assembled system and retain all three identities, exact binding
  revisions, qualification evidence and run records. Changes require explicit
  rebinding; an unavailable dependency must not cause silent substitution.

First proof: one context Cog runs through a separate Harness-only Cog bound
to cog-openrouter, with workbench performing the assembly. Current author and
evaluator Cogs carry their own interaction machinery; portability to an external
harness must be demonstrated, not assumed. A working Harness-only Cog and
consumer-contract conformance fixtures are prerequisites.

Starting material: the configurable-satisfier proposal in the OpenTeams
manifest-profile repository (an internal repository, not distributed),
the cog-openrouter reference host and its spec findings, and internal
architecture notes on the default stack, harness-as-satisfier and composition
points (not distributed).

**Alternatives and tradeoffs:** extend workbench as the existing reference client
instead of starting another executor project. Extract a reusable execution
library only if implementation demonstrates a need. Dynamic composition adds
admission, credential handling and provenance responsibilities beyond process
bring-up; scope and concrete contracts require a separate implementation task.

## Scorecard against the original client's gap record

(The nine numbered gaps below are the ones the earlier reference client, an
internal package that is not distributed, recorded as places it had to guess.)

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

## Implementation: goal-first suite and explicit composition (2026-09-07)

Trent authorized building the subscription Cogs, extending workbench, and adding
an Op designer feeding Cog building. This implements a bounded first version of
the future direction above; it supersedes that section's backlog-only status for
the capabilities described here. The name remains **cog-workbench**.

**Implemented:** a separate `/studio` screen and `suite` CLI; catalog discovery;
configuration-driven selector/binder; immutable host records; context/harness/model
composition with revocation and package-change checks; goal → Op-design proposal
→ missing-Cog briefs → author contract/source → evaluation plan → complete Smith
package → tests/cases → independent evaluator review. See `docs/tool-suite.md`.
The sequence is a building aid, not a persisted executable Op-manager definition.

The cognitive modules are independent Cogs: cog-op-designer, existing cog-author
and cog-build-evaluator. The separate cog-turn-harness supplies a minimal JSON
interaction with an independently bound OpenRouter model. cog-chatgpt and
cog-claude supply inseparable subscription Model+Harness access through official
vendor CLIs. Their advertised vendor tool restrictions are weaker than a portable
no-tools proof; they cannot satisfy bare-model evaluation requirements.

**Context portability:** the context Cog explicitly declares a composition bridge
that runs its existing input/output schemas and author-owned checks. No Smith
src machinery was changed. The bridge is maintained in workbench and copied
byte-identically into opting-in Cogs. Providers do not falsely advertise that
they independently execute consumer checks. Built packages opt into this same
bridge, respecting local-only contracts when present.

**Host authority:** provider candidates do not self-admit. Workbench checks request
correlation, composition, requirements, locality, features, package content and
separate dependencies. New turn providers support declaration evidence only;
workbench separately repeats local CLI readiness inspection and applies policy.
OpenRouter still uses its separate reference-host admission with fresh catalog
checks. Its manifest now declares host-adapter tasks in a distinct extension,
without turning admission into the provider's bind operation. Same-user filesystem
ownership is the local reference authority boundary, not protection from malicious
local package code. The new browser write surface requires a session token and
same origin. All suite operations are journaled; secret values are not persisted.

**Spec findings:** combined turns need nullable model references; combined providers
must not be forced into the model-inference protocol; a local declared command
transport must be distinct from the existing HTTP protocol. The unadopted draft
and vendored schemas were updated together. Vendor strict JSON output cannot
represent every open-ended schema document produced by the author/designer, so
those cases request JSON through context and enforce the complete schema locally.

**Alternatives and tradeoffs:**

- Keep cognitive design/author/review in Cogs instead of embedding prompts in UI
  code. Workbench retains deterministic host authority and explicit review gates.
- Use official CLIs and their login stores instead of implementing third-party
  subscription OAuth or extracting bearer tokens. CLI changes may require adapter
  updates and rebinding; subscription internals remain unverified.
- Use an explicit context bridge instead of altering or impersonating legacy
  model.json bindings. This records all component identities but requires opt-in.
- Vendor one small runtime into three independently installable Cog repositories
  rather than add a shared published package dependency now. Copy-identity tests
  and hashes make synchronization reviewable; a library can be extracted later.
- Use bounded local jobs and saved artifacts rather than an Op scheduler. There
  is no automatic publishing, autonomous repair loop or running of designed Ops.
- Existing inspector behavior and meeting-owned contract gaps remain separate.

Validation and live-test limitations are recorded in
`docs/verification-2026-09-07.md`. Pre-existing local edits to cog_package.py and
toml_compat.py were preserved.

The suite also offers an explicit **Install environment** action. This derives
installation from the loaded package's Pixi declaration and runs a fixed Pixi
install operation; it accepts no command text. Installation is separate from
packaging and testing so dependencies are visible and no generated task silently
installs them. No dependencies were added to workbench's own runtime.

## Live authoring timeout (2026-09-07)

The approved live workflow reached contract design, then whole-source authoring
exceeded the provider's 180-second limit. Subscription turns now have a bounded
600-second allowance; the workbench turn call allows 660 seconds so provider
cleanup can complete. Readiness checks remain 15 seconds, other operations keep
their existing limits, and timeout still kills the vendor process group and
accepts no partial output. Alternatives: split authoring into multiple contract
operations (larger API change) or silently retry (would conceal failures and
consume more subscription usage). A longer bounded call is the smallest repair;
latency remains visible and provider changes require a new binding revision.

## Concrete evaluator case inputs (2026-09-07)

A live plan returned matrices, output mutations and construction recipes in its
input objects. Workbench sends each input unchanged to the candidate; accepting
these would misreport unsupported procedures as candidate failures. Evaluator
checks now require each case input to satisfy the accepted candidate input schema,
using only local schema references. Its context states the single-invocation scope.
Workbench already revalidates the plan before invoking any cases.

Alternatives: implement a free-form test interpreter (violates declared-operation
boundaries), or add a typed multi-operation test protocol now (larger spec change).
The bounded repair retains direct invocation cases; invalid-input, output-mutation,
capacity and side-effect instrumentation need separate execution evidence. This
means a correct candidate may still receive insufficient_evidence, which is more
accurate than an unsupported pass or a false failure.

## 2026-09-21 — build pure code Cogs through the suite

The merge-findings replay must exercise designer → author → Smith → evaluator.
New briefs carry optional cog_kind; absent means legacy context. Procurement
stays existing/new, independent of implementation kind. Legacy unbound code
choices remain readable proposals but handoff refuses them with a redesign hint.
This preserves old context artifacts without pretending old code prose is a brief.

Accepted contracts and identities carry kind. Smith receives its existing
--kind flag; its compiler and shared runtime need no behavior changes. Workbench
transfers the authored snapshot and installs the composition bridge only for
context Cogs. Pure code evaluation invokes the declared default usage task and
records package identity alongside candidate-bound case evidence. Reaching code
Cogs are refused by this evaluation path until a grant-aware host contract exists.

Alternatives: hand-build this candidate (would repeat the drift); require a model
binding for code (misstates runtime identity); add model judgment to Smith (breaks
its deterministic role); support all external effects now (unnecessary for this
first vertical slice). The bounded extension retains trusted local code execution
and does not claim sandboxing, autonomous acceptance or general Op management.

The first full merge-findings source request timed out at 600 seconds through
both Claude and ChatGPT. Returning accepted schemas/contract/fixtures repeatedly
is unnecessary model work and invites transcription errors. The author now
supports explicit SHA-256 references to the accepted contract and supplied JSON
materials; executable code and tests must still be authored. Its exporter expands
and validates the complete snapshot. Workbench's snapshot operation obtains that
canonical evaluator request through the declared exporter. Alternatives considered:
lengthening every provider deadline (does not address duplication), hand-authoring
the candidate (bypasses the pipeline), or unverified file references (breaks source
identity). Hash mismatch, ambiguous materials, and implementation-code references
are refused. Evidence fingerprints always cover expanded content, never just refs.

Native case execution now preserves full stdout envelopes rather than using the
30,000-character display-log tail. The largest reference case exposed truncated
JSON masquerading as an invocation failure. Diagnostic logs remain capped; native
structured evidence retains the complete result. Alternative: reject large valid
results, which would constrain the candidate contract without a declared limit.

Native evidence marks an identity-checked envelope as observed even when it carries
an expected refusal or warning. Its explicit scope requires the evaluator to judge
actual behavior; it does not grant criterion acceptance. The evaluator's complete
case-category/criterion coverage rule applies to planning. Reviews may propose only
targeted reproducers, while full assessment and execution-evidence rules remain.
Requiring a repeated full plan at review rejected a useful live revise verdict.

The [worked build report](docs/merge-findings-pipeline-build-2026-09-21.md) records
the actual candidate, repaired test entry point, and documented reference divergence.

## 2026-09-21 — the builder lifecycle belongs to an Op

Trent clarified that the product is `op-cog-builder`, taking work through the
multi-Cog pipeline. Workbench remains its client and invocation environment.
The implementation plan (an internal planning note, not distributed; the
public roadmap is at
https://github.com/cogcloud-ai/cog-op-builder/blob/main/docs/roadmap.md)
defines the lifecycle and milestones. Smith already maintains shared Op machinery
0.6.6; `op-builder-smoke` verifies native execution, mapped handoffs, Track,
fail-stop and resume against the new code candidate.

Decision: reuse that machinery rather than add a Workbench-only executor or put
the whole build sequence into a code Cog. Existing suite helpers remain useful
until reusable build/verification request seams replace manual coordination.
Tradeoff: provider composition, artifact acceptance, and multi-step revision
cycles require explicit shared contracts; the existing change-list human Gate
and same-step repeats do not already implement them. No executable builder spec
is claimed before those dependencies are available.

## 2026-09-21 — first executable single-candidate builder

`op-cog-builder` now composes author → materialize → plan → verify → review
through shared Op machinery 0.6.6. It starts from an accepted pure-code contract,
stops after one review, and always labels acceptance as not granted. A successful
Op completion means the workflow ran; the evaluator's classification remains a
separate output. Automatic revisions and general artifact approval are deferred.

The provider seam uses opt-in `ask-composed` usage tasks on author/evaluator,
vendored from bridges/composed_usage.py. Workbench activates a pinned composition
in ignored `.op-composition.json`, which the Op runtime already hashes as part
of the consumer. The record also pins Workbench's host code. This avoids adding
provider-specific execution paths to the shared runner. Alternatives: extend
the runner with a second invocation protocol now, or package a proxy Cog that
would obscure the actual consumer identity. Tradeoff: this first host adapter
requires the sibling Workbench layout and reactivation after host/source changes.
Task data cannot configure the binding; packaged checks still surround each turn.

`cog-build-candidate` and `cog-verify-candidate` own two bounded deterministic
jobs, using the declared local-builder-host API. Materialization preserves full
source, refuses collisions and reconciles a completed receipt. Verification
records actual declared tests and cases, retaining failed evidence for review.
No worker owns the workflow or makes acceptance decisions. Host dependencies
and trusted local execution are explicit; automatic installation and arbitrary
commands are unsupported. Infrastructure code is hand-authored; model-generated
candidate evidence is recorded separately.

The live single-candidate Op completed after one rejected plan and one resume.
The evaluator had proposed a schema-invalid enum despite the executable-case
contract; its packaged checks and the Op Gate stopped execution. The prompt now
distinguishes schema-invalid negative tests (separate declared-test evidence)
from schema-valid semantic violations. Reactivation and native Op resume retained
the passed author/materialization work. Final review passed all 14 criteria;
the [qualification record](https://github.com/cogcloud-ai/op-cog-builder/blob/main/docs/implementation-2026-09-21.md)
retains the rejected plan, actual observations, and compatibility limitations.

## 2026-09-22: Builder-suite licensing

With OpenTeams authorization, use Apache-2.0 for the builder suite, including
Workbench. Compared with retaining BSD-3-Clause, this aligns the suite and
adds explicit contributor patent terms at the cost of additional notice
obligations. Preserve third-party terms and historical BSD releases. This
changes package identity; existing pinned compositions may require renewed
admission and activation.

## 2026-09-23: Public preview and reproducible setup

Publish the builder suite using explicit sibling checkouts and model-free CI.
A central manifest and setup guide replace private-workspace orientation for
new contributors. Keep existing declared operations and the Op-owned lifecycle;
registry installation and sandboxing remain separately tracked work. Preserve
meaningful machinery history instead of a blanket squash, because provenance
records refer to those commits. Local run records and bindings remain ignored.
