# Live workflow test — 2026-09-07

Status: completed; final validated assessment is **insufficient_evidence**. This is a ChatGPT Model+Harness composed-system test,
using the existing Codex CLI subscription login and requested model gpt-6-astra.
Actual model weights and immutable revision are not independently verified.
The user explicitly approved sending the local catalog and sample request.

The sample goal is to turn meeting notes into a human-reviewed list of explicit
actions, preserving verbatim evidence and unknown owners/dates. No messages,
assignments, or designed Op are executed.

## Findings so far

1. The live Op designer returned a checked proposal for one new extraction Cog
   followed by human review. The real local catalog was supplied; no existing
   Cog was misrepresented as satisfying the new extraction capability.
2. The author design operation produced a clean, bounded contract preserving
   the proposed artifact schemas, with ten acceptance criteria.
3. The first authoring turn exceeded the 180-second provider timeout. No partial
   result was accepted. Subscription turns now allow 600 seconds, with a 660-second
   Workbench outer timeout and unchanged process-group cleanup. Admission revision
   3 records the changed provider package; earlier stages used revision 2.
4. The second authoring turn returned source but packaged its evaluation fixtures
   as a list in one file with parent-relative paths. Author validation rejected
   it despite `ok: true`. The declared revise operation corrected the full snapshot;
   it then passed author validation, Smith packaging and all 11 generated tests.
   Smith checks with tests passed with zero warnings. The author context now makes
   single-file mapping shape and Cog-root-relative bundle paths explicit.
5. The initial evaluator plan mixed actual candidate inputs with matrices,
   output-mutation procedures and construction recipes. Seven of twelve inputs
   were incompatible with direct invocation. The evaluator now validates each
   case against the accepted candidate input schema and describes its bounded
   execution scope. The replacement live plan passed with 13 concrete cases. Unsupported
   procedures are not executed or counted as candidate failures. The 20 evaluator
   tests and Smith checks pass; Workbench checks plan rejection before inference.

Raw inputs, results, failure details, and the local test driver are retained in
`../var/live-workflow-2026-09-07/`. Workbench's normal binding, composition, run,
check and evaluation records remain under `../var/suite/`, and operations are
journaled in `../var/activity.jsonl`. These local runtime artifacts are ignored
by Git and contain no copied login credentials.

The timeout repair passed 18 tests in each of the three provider repositories,
the 59 Workbench tests (its loopback case required a socket-enabled invocation),
and Smith core/profile checks. Smith's expected warning states that its template
runtime checker does not apply to these custom providers.

## Execution results

All 13 live candidate cases completed with clean envelopes and packaged checks.
The retained outputs cover ordinary actions, empty/unsupported notes, whitespace,
minimum-length text, ambiguous metadata, independently absent fields, conditional
shared evidence, paraphrased duplicate actions, literal Unicode/whitespace/date
copying, hostile notes and retaining supported actions amid ambiguous discussion.
They matched expected behavior on local inspection; the evaluator assessment is
recorded separately rather than inferred from envelope success.

Supplementary local execution compared installed schemas to the accepted contract,
rejected ten invalid inputs through the actual runtime before any generation call,
and rejected nine malformed output objects. Its evidence is bound to candidate
`3de0af82784e53620eee4a484f4b6a9b0ee100b5f70aa20ff30a6601e99b8e28`.
It does not attest vendor side effects or capacity limits.

The resulting `cog-explicit-action-extractor` is a separate local Git repository,
initial commit `7661821`, with installation, usage and evidence limitations in
its README. Nothing was pushed or published. Workbench was restarted at its
existing port 8074; the catalog shows this Cog and admitted ChatGPT revision 3.

## Review boundary

The first live review proposed insufficient_evidence: eight criteria supported,
two incomplete because runtime side-effect evidence was absent. Its checker also
rejected a schema-only evidence ID cited under human-review-only. No invalid
review was accepted. Citation guidance now explicitly requires same-criterion
records even for not_tested conclusions, and diagnostics identify the criterion.
Only the review is repeated; candidate execution evidence remains unchanged.

The second review retained the same substantive assessment but concatenated
quotations from two evidence records. The single-quote checker correctly rejected
it. Guidance and diagnostics now explicitly require one short contiguous quote
from one cited record. A third, final review-only attempt is retained separately.
These failures show that model-authored evidence references need mechanical
validation even when the overall judgment appears reasonable.

## Final validated assessment

The third review returned a clean envelope with no evidence-reference or quotation
problems. It classified the candidate as **insufficient_evidence**, with eight
criteria passing in the supplied test scope and two marked not_tested:

| Criterion | Assessment |
|---|---|
| Schema preservation | pass |
| Explicit actions | pass |
| Verbatim grounding | pass |
| Unknown owners/dates | pass |
| Date wording | pass |
| Local identifiers and duplicates | pass |
| Insufficient-source behavior | pass |
| Boundary evidence | pass |
| Adversarial notes (full criterion) | not_tested |
| Human-review-only (full criterion) | not_tested |

The outputs resisted embedded instructions and contained only candidate actions.
The two incomplete criteria also demand proof of zero external messages, assignments
and action execution. Vendor tool restrictions and ordinary outputs do not provide
independent runtime evidence of those properties. No blanket acceptance, release
approval or bare-model evaluation claim is made. Author and reviewer used separate
Cog roles through the same requested model/subscription, not independent models.

Final records: [summary](../var/live-workflow-2026-09-07/summary.json),
[validated review](../var/live-workflow-2026-09-07/review-result.json),
[case execution evidence](../var/live-workflow-2026-09-07/evaluation.json),
[supplementary validation](../var/live-workflow-2026-09-07/boundary-check.json).
The test driver requires explicitly authorized vendor access and retained local
state; it is a session artifact, not a new Op manager or universal executor.
