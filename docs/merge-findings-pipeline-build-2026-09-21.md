# Merge Findings: fresh code Cog through the builder pipeline

The candidate is [`cog-merge-findings-candidate`](https://github.com/cogcloud-ai/cog-merge-findings-candidate).
It was designed and authored by the builder Cogs, packaged by Smith, and tested
through Workbench. The original merge Cog (an internal package, not distributed)
remains unchanged at `398c1576225c1f27cd842d9837701fe2439affce` and is the
"reference" compared against below. This is a candidate build, not a
replacement of the reference or a publication decision.

The final live evaluator review returned **pass on all 14 criteria**, with no
findings and a clean checked envelope. This is an assessment of the supplied
source and execution evidence, not a release authorization.

## The distinct job

Merge Findings consolidates detector outputs across batches and repeated runs.
It deduplicates equivalent findings, counts support once per accepted repeat,
preserves source references and disagreement, and folds inferred dependency
evidence into an equivalent stated dependency according to explicit rules.
It does not detect new relationships or decide which conflicting judgment is true.

This is a reusable boundary between cognitive detection and downstream proposal
creation. Its schema and semantic contract checks produce problems for the
surrounding Op's Gates; independent Guards can assess system requirements.
The implementation has no model dependency, external reaches, or persistent
memory. The code-only designation makes that absence explicit. The reasoning
happened while defining and building the rules; runtime work is deterministic.
See [Smith's code-Cog guidance](https://github.com/cogcloud-ai/cog-smith/blob/main/BUILDING_COGS.md).

## What actually ran

1. `cog-op-designer` produced a new code-Cog brief through its declared composition.
2. `cog-author` designed the work contract. A design revision resolved an
   inconsistent permutation-invariance claim and clarified tie and dependency rules.
3. `cog-author` generated the full implementation and tests from that contract,
   reference documentation, schemas, and synthetic fixtures. Reference Python
   implementation source was not supplied to the author.
4. Workbench used the author's validated exporter, then Smith's existing
   `new --kind code` and checker. The candidate is a complete package.
5. `cog-build-evaluator` independently planned 27 cases covering 14 criteria.
   Workbench executed those cases through the candidate's declared native task.
6. The first live review requested changes: the test module needed its standalone
   import setup, the measured ordering difference needed explicit documentation,
   and schema/invalid-input criteria needed corresponding execution evidence.
7. `cog-author` revised the tests and documentation. A source diff confirmed
   `src/task_logic.py` remained byte-identical. Smith packaged the revision;
   Workbench installed its environment and collected fresh execution evidence.
8. A fresh `cog-build-evaluator` review assessed the revised snapshot and its new
   evidence. All 14 criteria passed; no follow-up cases or source findings remain.

Designer and evaluator turns used the Claude provider with the requested `sonnet`
selector. Successful source authoring used the ChatGPT provider with requested
`gpt-6-astra`. These are recorded provider configurations, not weight attestations.
Separate Cog roles and providers do not prove independent reasoning or correctness.
Candidate repairs went through author/revise; no manual implementation patches
were inserted into the candidate.

## Verification

| Check | Result |
|---|---|
| Candidate's declared test task, after environment installation | 13 tests pass, including table-driven malformed input, semantic mutations, schema discrimination, and a 10,000-repeat case |
| Smith check with tests | Pass; zero errors/warnings |
| CogSpec validator | Pass |
| Evaluator-planned cases | 27 native invocations, 49 criterion-linked observations; observations are not automatic acceptance |
| Final live evaluator review | All 14 criteria pass; no findings; checked envelope has no problems |
| Portable shared fixtures against both implementations | 5/5 normalized matches |
| Captured reference cases | 51/54 normalized exact matches; 54/54 relationship/provenance matches excluding IDs and row order |
| Reference's own existing suite | 85/86 pass; one existing fixture for a downstream consumer Cog is stale against that consumer's current schema |
| Builder component tests | Designer 11, author 23, evaluator 21, Workbench 63 pass |
| Provider runtime suites | 105 tests per provider package; ChatGPT and Claude each have one expected skip |

The comparison includes exact payload, success/error code, and the set of problem
check/severity pairs. Three reference cases (28, 48, 49) differ in finding IDs and
row order: the reference sorts dependency edges by `(blocked, blocking)`, while
the accepted candidate contract sorts by `(blocking, blocked)`. The underlying
relationships and paired provenance match. This is explicitly documented in the
candidate; exact interchangeability of finding IDs is **not** claimed.

Problem diagnostic text also differs in six of the 54 cases. Both complete
problem lists are retained in `problem-detail-comparison-v2.json`; check/severity
matches do not assert prose equality. The reference fixture drift remains visible
as a candidate-test warning and in the recorded baseline failure.

Final source fingerprint (accepted contract plus sorted authored files):
`d0b5846667f25105119d0d632814315d243c2f5e055d697cbea0c4e4bf6f299c`.
Installed package fingerprint used for fresh execution:
`8160d61d94e995929b4096ecc09315689a02fcb81fb99f09fb85dfbe4e164e31`.

## Pipeline improvements exposed by this build

- Designer briefs now distinguish implementation kind from new/existing selection.
  An unbound legacy code step cannot silently bypass a real build brief.
- Author contracts, source checks, and export support pure code Cogs. Context
  remains the backward-compatible default. Code packages need no model prompt.
- Large unchanged JSON materials and accepted contracts can use SHA-256 references.
  The exporter expands them from supplied input, verifies hashes, and produces the
  full source snapshot. Code and tests still require authored source text.
- Workbench passes kind to Smith, executes pure code without a model binding,
  binds evidence to source/package fingerprints, and preserves complete native
  envelopes. Large outputs previously hit a log truncation limit.
- Evaluator reviews can return targeted follow-up cases without regenerating the
  full planning matrix. Every criterion still needs a grounded assessment and
  passed execution evidence to qualify for a pass.
- Provider readiness now accepts successful status output written only to stderr,
  fixing the Codex login-status check. The shared runtime fix was made upstream
  and vendored identically into the subscription provider Cogs.

Two full-source attempts exceeded the 600-second provider deadline before compact
references were introduced. The first package test before installation lacked
dependencies; after installation it exposed the real source import failure.
Those failures are retained. The first evaluator review also hit an overly broad
case-coverage check; its recorded model result was explicitly revalidated after
the checker repair, not relabeled as another model run.

Smith received no new model behavior or runtime changes for this build. These
changes strengthen the multi-Cog path. General Op lifecycle management and code
Cogs with external reaches remain outside this implemented slice.

## Replay and local evidence

The candidate tests are self-contained; no reference checkout or provider account
is required to run it:

```sh
cd cog-merge-findings-candidate
pixi install
pixi run test
pixi run run -- --bundle examples/sample-bundle.json
```

The complete local build trail is in Workbench's local `var/merge-findings-build/`
(ignored by Git, not distributed). Principal records:

- `designer-result.json`, `designer-handoff.json`, and `contract-decision-v2.json`;
- `author-request-v4.json` / `author-result-v4.json` for first authored source;
- `author-revise-request-v5.json` / `author-result-v5.json` for repaired source;
- `source-snapshot-v5.json` for expanded source;
- `evaluator-contract-plan-result.json`, `executed-cases-v2.json`, and
  `evaluator-review-request-v2.json` for plan and fresh review evidence;
- `evaluator-review-v2.json` for the final live pass and `completion-record.json`
  for the local handoff fingerprints;
- `candidate-tests-v2-installed.json`, `candidate-smith-check.json`,
  `candidate-core-check.json`, `differential-v2.json`, and
  `shared-fixture-comparison-v2.json` for observed results;
- `reference-tests.json` and `problem-detail-comparison-v2.json` for limitations;
- `build_step.py`, `verify_candidate.py`, and `review_candidate.py` for local replay.

The failed first candidate is archived under
`var/merge-findings-build/candidates/v1/`; its relocated environment is not a
portable installation. The current root candidate has its own fresh installation.
Local paths and provider binding records in the raw trail should not be treated
as a portable release bundle. No private issue data was used. Generated code was
run in the trusted local workspace; this workflow does not provide a sandbox.

## Public-preview evidence scope

This is a historical qualification summary. References to `runs/`, `var/`, or
workspace-relative artifacts identify private local execution records; those
records are not distributed. The public model-free tests are reproducible
checks of mechanics, not a replay or independent verification of the live model run.
