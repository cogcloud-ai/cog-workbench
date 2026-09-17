# Verification: Cog tool suite, 2026-09-07

This is a bounded reference implementation. Deterministic integration tests,
live subscription transport checks and live task quality are distinct evidence.

## Completed

- cog-chatgpt: 18 deterministic tests after the live timeout repair.
- cog-claude: 18 deterministic tests.
- cog-turn-harness: 18 deterministic tests.
- cog-op-designer: 10 deterministic tests.
- Existing cog-author: 15 tests; cog-build-evaluator: 20 tests after concrete-case validation was added.
- OpenRouter reference: 30 tests, including its synthetic local HTTP gateway.
- Binding profile: 10 schema tests, including command transport and combined
  null model references.
- Workbench: the existing 41 tests plus 14 suite tests, one actual local HTTP
  composition test and three browser-boundary tests (59 total). These cover declaration-derived operations, candidate and
  admission separation, exact references, corruption, revocation propagation,
  context preflight/postflight, Op-design handoff, full source packaging and
  evaluator evidence handoff. The local HTTP test invokes real context/harness
  subprocesses against a synthetic model response, retaining gateway provenance.
- Smith core/profile checks with tests passed for designer, author and evaluator.
  Custom turn providers pass core/profile; the expected warning states Smith's
  template-runtime checks do not apply. Their dedicated suites run separately.
- An action-extractor source fixture was packaged through the complete author
  exporter → Smith → full-source-transfer path; its three tests passed. It was
  a disposable integration package, not a new live-model-authored deliverable.
- Browser verification: `/studio` loads its catalog, runs a package check, and
  admits a ChatGPT Model+Harness binding. The original inspector links to it.
- **Live synthetic ChatGPT checks passed** using Codex CLI 0.153.4, the existing
  ChatGPT login and requested model `gpt-6-astra`. Both native structured JSON and
  the open-schema/prompt JSON path returned `{"ready": true}`. No workspace catalog,
  file contents or user task material was sent in these synthetic checks.
  Observed model identity remains unverified; success does not attest weights.

## Not completed / limits

- Claude Code 2.1.263 is installed, but `claude auth status` reports no active
  login. Its adapter is covered by deterministic command/output tests; live
  Claude invocation requires the owner's subscription sign-in.
- The user subsequently approved the local catalog/sample transmission and the
  full live ChatGPT workflow was exercised: design → contract → author/revise →
  package → concrete evaluation cases → review. See
  [the live workflow report](live-workflow-2026-09-07.md) for failures, repairs,
  retained evidence and the final assessment. All 13 live candidate cases passed
  envelope/packaged checks. The validated review supports eight criteria and
  leaves two incomplete for missing side-effect evidence; no blanket acceptance.
- No real OpenRouter inference was used in this session; the new separate-harness
  path was tested with a local synthetic gateway. Supply the owner's API key and
  gateway token for a real run.
- Environments/locks were generated on this Mac. Tests here used the installed
  macOS Python environments; no Linux or Python 3.10 execution claim is made.
- All new Cogs have separate local repositories. No GitHub repos were created,
  no pushes or publication were performed, and no login/background service was
  installed. The local workbench verification server is not an auto-start service.

The existing workbench suite emits resource warnings for a couple of its old
process tests; they do not fail. Pre-existing local changes to cog_package.py and
toml_compat.py were preserved and included in regression testing.
