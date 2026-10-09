# Cog Workbench: design and building tools

Workbench is the suite’s local client. Its selector/binder is one component. The Op designer
produces a proposal and Cog-building inputs; this is not an Op manager,
scheduler, deployment service or general workflow execution engine.

The intended build lifecycle belongs to `op-cog-builder`; Workbench will be its
client and invocation environment. See the [Op implementation plan](https://github.com/cogcloud-ai/cog-op-builder/blob/main/docs/roadmap.md)
and [basic shared Op execution example](https://github.com/cogcloud-ai/op-builder-smoke/blob/main/README.md).
The manual suite workflow below remains available while the Op seams are built.

The first [executable Cog Builder Op](https://github.com/cogcloud-ai/op-cog-builder/blob/main/README.md) now takes
an accepted pure-code contract through one complete candidate review. Activate
admitted bindings with `suite activate-composition --context cog-author
--binding-id ID --revision N` and the same command for `cog-build-evaluator`.
Their declared `ask-composed` usage tasks work with the existing shared Op runtime.
The Op owns sequencing; Workbench supplies composition and local execution services.

For a worked code-Cog build, see the [Merge Findings pipeline report](merge-findings-pipeline-build-2026-09-21.md),
including the author revision, native tests, and reference-comparison limits.

## Start here

```sh
cd cog-workbench
pixi install
pixi run serve
```

Open `http://127.0.0.1:8071/studio`, or choose **Design & build** from the existing
package inspector. The existing inspector and its declared operations still work.

1. Connect a provider. For ChatGPT, log into Codex with `codex login`; for Claude,
   use `claude auth login`. Select an explicit model your subscription supports.
2. For OpenRouter, supply `OPENROUTER_API_KEY` and `OPENROUTER_COG_TOKEN` in the
   workbench launch environment. Bind an exact model and upstream, start the
   model gateway, and bind `cog-turn-harness` to that model revision.
3. Describe an outcome, success criteria and constraints. Select an admitted
   interaction binding and design an Op.
4. Review the steps and assumptions. Accept the proposal to prepare one author
   design request per missing Cog. Review and accept each resulting Cog contract.
5. Author source, plan evaluation and package the complete source with Smith.
   Package checks run before the destination is created. Packaging does not
   execute generated tests or accept the Cog's behavior.
6. Run packaged tests and the planned cases, then ask cog-build-evaluator to
   review the supplied evidence. Case completion only establishes envelope and
   packaged-check success; the review assesses the acceptance criteria.

The example model IDs are selectors, not quality recommendations. Subscription
model aliases and provider internals may change. CLI version/package changes
invalidate bindings. Tests of a subscription composition are system tests, not
bare-model benchmarks.

## Components

| Component | Responsibility |
|---|---|
| cog-op-designer | Outcome → proposed Op, capability needs, grounded reuse, missing-Cog briefs |
| cog-author | Brief → work contract → complete authored/revised source |
| cog-build-evaluator | Independent evaluation planning and evidence review |
| cog-smith | Final Cog packaging and package checks |
| cog-turn-harness | Single JSON turn using a separate OpenRouter model binding |
| cog-chatgpt | ChatGPT subscription plus Codex CLI harness |
| cog-claude | Claude subscription plus Claude Code harness |
| workbench selector/binder | Discovery, requirement filtering, host admission and exact revisions |
| workbench context bridge | Consumer's own checks before/after an external turn |
| workbench building tools | Handoffs, source transfer, tests, case execution and evidence records |

Cogs own design, authoring, assessment, and bounded deterministic work. Workbench owns local authority, admission, operation
invocation and evidence storage. The selector returns configurable providers,
not admitted satisfiers, until configuration and qualification are complete.
The current host supports the three supplied turn providers and the separate
OpenRouter reference-host adapter; it is not a universal provider resolver.

## CLI and reusable artifacts

All suite commands return JSON. Package names are relative to the workspace
(the parent of the sibling checkouts), while request filenames are relative to the current shell directory.

```sh
pixi run suite -- catalog
pixi run suite -- bindings
pixi run suite -- bind --provider cog-chatgpt --request ../cog-chatgpt/examples/bind-request.json
pixi run suite -- compose --context cog-op-designer --binding-id binding-cog-chatgpt --revision 1
```

The compose result includes `record_path`. Use that saved document directly:

```sh
pixi run suite -- invoke --composition /absolute/path/to/composition.json --bundle ../cog-op-designer/examples/sample-bundle.json
pixi run suite -- handoff --request design-request.json --envelope design-result.json
pixi run suite -- package --request author-request.json --envelope author-result.json --destination cog-my-worker
pixi run suite -- check --cog cog-my-worker
pixi run suite -- test --cog cog-my-worker
pixi run suite -- eval --cog cog-my-worker
pixi run suite -- revoke --binding-id binding-cog-chatgpt --revision 1
```

`invoke` works for the designer, author, evaluator and packages built by this
workflow. To revise source, invoke cog-author with operation `revise`, the same
accepted contract, previous source snapshot in `materials`, and explicit feedback.
`eval` is the Cog's native declared evaluation operation and uses its installed
native model binding. The screen's **Run planned cases** instead uses the selected
external composition and produces a fingerprinted evaluator review request.

New packages need their declared environment installed before testing or serving
outside the development environment. Choose **Install environment**, run `pixi run suite -- install --cog cog-my-worker`, or run `pixi install` in the package. This explicit host operation uses only the loaded package’s declared Pixi environment. Workbench
prefers each Cog's installed Python and otherwise uses the workbench interpreter;
missing dependencies are reported, never installed silently by a generated task.

## Local storage and authority

`var/suite` is owner-only. Bindings retain exact requests, configurations and
credential references, package content digests and host admission evidence.
Each ID uses monotonically increasing immutable revisions. Revocation and
package changes make dependent compositions unavailable; there is no automatic
model replacement. OpenRouter's original host admission remains authoritative
for its gateway; workbench checks it again before dependent use.

Composition and run records retain context, harness and model identities. Run
records store input/output hashes and provenance; web job results also retain
Cog outputs for review. Credentials are never stored by the suite. Subscription
credentials remain in vendor login stores. OpenRouter keys/tokens currently
come from environment variables and must be supplied again to a new shell or
through the owner's secret manager. Keychain integration remains future work.

The owner trusts local Cog code. Declared operations and packaged contract checks
execute code with that user's authority; this is not a sandbox for malicious
packages. The new browser action endpoint requires a session token and matching
origin. Workbench stays on loopback and is not a public or multi-user service.

## Current limits

- Binding qualification for the new turn providers is declaration-level. The
  host validates constraints and separately inspects the installed CLI; it does
  not prove immutable weights, zero hidden vendor context or all tool behavior.
- The pure harness supports OpenRouter's admitted loopback gateway, text/JSON,
  no tools and no memory. General tools, grants and agent loops need new contracts.
- Catalog discovery currently covers direct workspace children. Reuse suggestions
  check declared capability/output vocabulary and fingerprints; they are not
  semantic proof of compatibility. The designer checks artifact flow, not full
  JSON-Schema subsumption across an existing Cog's input/output contracts.
- Building supports bounded context Cogs and pure code Cogs through cog-author/Smith.
  Multi-Cog build scheduling, automatic repair loops, publishing and Op execution
  are outside this implementation.
- Browser results are saved locally, but the in-progress screen is not restored
  automatically after reload. Reuse saved artifacts through the CLI.
- The same model can author and review through separate Cogs. That separation
  of roles is not proof of independent model judgment.

See `verification-2026-09-07.md` for what was actually tested.

## Pure code builds

A new designer brief can set `cog_kind: code`; the handoff carries `kind: code`
to author design. Accepted contracts and author identities retain it; the identity
omits `model_cog`. Old artifacts without kind retain context semantics. Legacy
proposal choices of kind `code` must be redesigned as `new` with a code brief
(or an existing catalog choice) before handoff.

Packaging selects Smith's code template and transfers the complete source. Native
case execution uses the declared default usage task, no interaction binding, and
records the whole package fingerprint. `suite evaluate` accepts omitted binding
flags for code Cogs. The author and evaluator themselves still need a provider.

The current code path supports pure Cogs only: empty `requires` and `reaches`.
It is trusted local execution, not a sandbox. Native evidence status describes
whether a valid candidate envelope was observed, including expected warnings or
refusals; it does not accept the behavior. The evaluator compares actual payload,
problems and errors to each criterion. Changed source is refused before execution;
package changes during cases invalidate the run.

## Expanded source snapshots

Large author outputs may refer by SHA-256 to their accepted contract and supplied
JSON schemas instead of repeating them. Before planning evaluation, obtain the
complete source through the author's declared exporter:

```sh
pixi run suite -- snapshot --request author-request.json --envelope author-result.json
```

The result is an evaluator plan request with full contract and file contents.
Studio uses this same operation. Packaging and case execution also verify and
expand the references. Hash mismatch or an ambiguous material name refuses the
handoff. References never access local paths, and executable code cannot use
references. The evaluator's fingerprint covers the expanded bytes.

### Activate every composed Cog in an Op

From Workbench, after admitting the binding:

```sh
pixi run suite -- activate-op --op op-cog-builder --binding-id BINDING_ID --revision 1
```

Use a workspace-relative Op path (the default workspace is Workbench's parent).
This validates the Op with public Smith, checks each step's declared Cog identity,
and activates each `ask-composed` consumer once. Other usage tasks are skipped.
The result lists `activated` and `already-current` consumers and their steps.
Every composed consumer must accept the selected binding; incompatible Cogs fail
preflight before installation. An Op mixing chat and System One capabilities
needs separate compatible activations with `activate-composition`.

New installed compositions and binding records use workspace-relative paths.
Keep suite state inside the workspace (the default `cog-workbench/var/suite` does
this), and move the whole workspace together. Reinstall each declared Pixi
environment with `pixi install --locked` after relocation. Owner permissions, integrity,
provider dependencies, package fingerprints and revocation are still checked.
After this fingerprint-format upgrade, re-admit all providers with new binding revisions and reactivate consumers. Records from before the upgrade can be revoked, but cannot be used until
the provider is re-admitted and consumers are reactivated. Credentials remain local
configuration and are never copied by these commands.

Edits to tests, examples, evals, prose or a lockfile do not invalidate a composition.
Manifest, context, source, scripts, binding and contract edits do. A changed host
still requires explicit reactivation; the stale error prints the fixing command.
Do not mistake these fingerprints for an environment attestation or a sandbox.

### Saved builds in Studio

Open `/studio`, connect an interaction provider, then use **Build a Cog with saved progress**.
Enter a bounded brief and owner, review the default repair paths, and choose
round/model-turn budgets. **Start saved build** activates the builder's model
consumers and starts its native cycle. It pauses on contract acceptance before
source is authored. Read the artifact, name the person deciding, then accept or
reject; rejection requires a reason. Independent review and verification are
shown beside the final candidate before its separate acceptance Gate.

Select a saved build after reload or server restart to recover its steps,
evidence and pending choices. **Resume after interruption** retries interrupted work
through the same native cycle. Exhausted, rejected and completed cycles offer no
continuation. A disappeared browser job is not permission to launch replacement
work: refresh saved builds and inspect the durable Track.

These controls delegate to `op-cog-builder`'s declared `cycle` and Smith's
`op-decide` tasks; install their compatible public revisions first. Model-turn
units cap declared invocations, including retries, and do not estimate invoices.
The optional Docker verification policy is configured in the builder request;
the simple form currently uses explicit trusted-local verification defaults.
