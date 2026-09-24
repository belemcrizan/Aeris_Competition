# Aeris Competition: a graph-guided, uncertainty-gated SWE agent for Gemma 4

This is a submission and research repository for the [Google – Gemma 4 Developer Agent Competition](https://www.kaggle.com/competitions/gemma-4-developer-agent). It is an independent project: it borrows principles from AERIS (closed-loop control, evidence-based intervention, explicit uncertainty, observability) but no code.

## 1. Problem

Given an issue in an unfamiliar Python repository, an autonomous agent running `gemma-4-31b-it-qat-w4a16-ct` must produce a patch that passes hidden validation tests. All tasks share a single 12-hour budget.

## 2. Competition (verified facts)

- The submission is `submission.zip` with `agent.yaml` at the root. It is a Google ADK Agent Config with sandbox restrictions, plus optional `prompts/`, `configs/`, `sub_agents/`, `skills/` and `adapters/`.
- Every agent must use `gemma-4-31b-it-qat-w4a16-ct`. Optional PEFT LoRA adapters are selected per agent with `adapter: <name>`.
- Tools: `run_command`, `read_file`, `edit_file`, `write_file`, `submit_patch`, `get_status`, `search_similar_code`, `get_code_neighbors`, `get_code_subgraph`, plus skill scripts.
- Scoring is PASS/FAIL per issue: the patch is applied, the task's `test_patch` is applied, and pytest runs.

The full requirement matrix, with sources and status, is in [docs/COMPETITION_REQUIREMENTS.md](docs/COMPETITION_REQUIREMENTS.md). **`HARNESS_README.md` and `sample_submission/` were not accessible (they need a Kaggle login).** As a result, the YAML syntax for tool references and the way skills are attached are UNVERIFIED. The closest authority we could run, google-adk 2.9.2, accepts every variant; its findings are in [docs/OFFICIAL_ARTIFACT_AUDIT.md](docs/OFFICIAL_ARTIFACT_AUDIT.md).

**Project status** (computed from [docs/gaps.yaml](docs/gaps.yaml)): see [docs/STATUS.md](docs/STATUS.md) and the full ledger in [docs/GAP_CLOSURE.md](docs/GAP_CLOSURE.md).

## 3. Research hypothesis

> Uncertainty-gated, graph-guided repository exploration improves the patch success rate and efficiency of a local agent under a fixed budget.

The hypothesis is broken into falsifiable sub-claims H1 to H6, each with refutation criteria, in [research/hypothesis.md](research/hypothesis.md).

## 4. Architecture

The agent is a single ADK `LlmAgent` whose system prompt is composed from switchable modules, plus four standard-library skills that run inside the task sandbox. Their state lives under `/tmp`, never in `/workspace`.

```
issue → localize (grep │ search_similar_code → locate_symbol) → bounded graph expansion
      → hypotheses + ledger → uncertainty gate → minimal patch → run_tests (signature)
      → belief update / retry (≤3) → review_diff → submit_patch
```

| Skill | Scripts | Purpose |
| --- | --- | --- |
| navigation | `locate_symbol.py`, `find_tests.py` | Graph node id to `file:start-end`; rank relevant tests |
| ledger | `ledger.py` | Hypotheses, evidence, entropy, budget mode, recommended action |
| testing | `run_tests.py` | Compact pytest report, failure signature, repeat detection |
| review | `review_diff.py` | Flags scratch files, test edits, debug output, CRLF churn and oversized diffs |

Design rationale, the gate thresholds and the context policy are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 5. Repository structure

```
submission/            source of the archive
  agent.yaml           rendered FULL variant (generated; do not edit)
  prompts/system.md    rendered FULL prompt (generated)
  prompts/modules/     prompt modules (edited by hand; not shipped)
  configs/sampling.yaml
  skills/{navigation,ledger,testing,review}/
experiments/
  components.yaml      ablation units: tools + prompt modules + skills
  configs/*.yaml       variants: B0..B5, FULL, ABL_*
aeris_comp/            offline tooling: validator, builder, scorer, metrics, taxonomy,
                       telemetry, data split, ADK conformance
scripts/               build_submission.py, validate_submission.py, run_experiment.py,
                       adk_conformance.py, make_split.py, make_tables.py, generate_docs.py
tests/                 UNIT and LOCAL_INTEGRATION tests (no harness needed; docs/TESTING.md)
docs/                  requirements, gap ledger and status, audits, validator codes, telemetry,
                       budget, security, scorer fidelity, release, architecture, experiments
research/              hypothesis, methodology, metrics, ablations, threats, results, paper/
dist/release_manifest.json  hashes of every variant archive (checked by CI)
adapters/README.md     LoRA policy (no adapter yet)
```

## 6. Quick start

```bash
python -m pip install -r requirements-dev.txt
python -m pytest                                   # local test suite
python scripts/build_submission.py                 # -> dist/submission.zip (FULL), validated
python scripts/validate_submission.py dist/submission.zip --strict
```

**Official artifacts** (HARNESS_README, sample submission, tasks) need a Kaggle login. Put them in `external/competition/` as described in [docs/HUMAN_HANDOFF.md](docs/HUMAN_HANDOFF.md), then run `python scripts/competition_bootstrap.py` (`make competition-audit`). It audits them, freezes the dev/held-out split and prints the next command: prepare **B0** (not FULL) for the first real harness task.

`make check` runs lint, tests, the sync and generated-docs checks, packaging and verification, where `make` is available. With `pip install google-adk==2.9.2`, `python scripts/adk_conformance.py dist/submission.zip` validates the archive with ADK's own parser and skill loader.

## 7. Experiments

B0 is the vanilla agent and the first harness candidate: issue → inspect → reason → edit → test → `submit_patch`. B1 to B5 add one component at a time; FULL adds the reviewer. No variant after B0 is enabled until B0 has a measured baseline. `scripts/run_experiment.py` freezes variants, scores harness predictions locally, and compares runs with a paired McNemar test. See [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md).

## 8. Metrics

The primary metric is PASS rate (with a Wilson CI). Secondary metrics are time, tool calls, changed LOC and files, retries, and exploration and validation cost. Failures get a primary and optional secondary labels from a 23-category taxonomy. Localization (Recall@k, MRR) and calibration (AUROC, Brier, ECE) metrics are implemented and tested. Skills emit telemetry in a fixed 20-event schema ([docs/TELEMETRY.md](docs/TELEMETRY.md)). See [research/metrics.md](research/metrics.md).

## 9. Submission generation

`scripts/build_submission.py` stages a variant and validates the tree. It then writes a deterministic zip and validates the archive again: root layout, includes, models, tools, adapters, skills, ADK placeholders, secrets and junk files. Each issue is an ERROR (official or ADK rule), a WARNING (risky, unverified or our policy, where blocking policy checks such as secrets stop the build) or INFO; see [docs/VALIDATOR.md](docs/VALIDATOR.md) and [docs/SUBMISSION.md](docs/SUBMISSION.md).

## 10. Current results

**Not yet measured.** No variant has been run against the competition harness or model. The only validated claims are local:
- the archive builds and passes validation for all 12 variants;
- google-adk 2.9.2 accepts every variant's `agent.yaml` and all four skills;
- the skill scripts work with every argument form ADK's `run_skill_script` produces, including inside ADK's own wrapper code;
- the test suite passes;
- `python scripts/competition_bootstrap.py` exits 3 until official artifacts are placed in `external/competition/`.

## 11. Limitations

- Tool-reference YAML syntax and skill registration are unverified until `sample_submission/` can be compared (R-TOOLS-2, R-SKILL-3).
- The local scorer approximates the official grader (test selection, apply command).
- Hypothesis weights are model-reported and uncalibrated. The gate thresholds are untuned priors.
- The graph "relevance score" is a conceptual model, not a computed quantity.
- No harness traces yet, so time, tool-call and exploration metrics cannot be extracted.

## 12. Roadmap

1. Human: accept Kaggle rules and put official artifacts in `external/competition/` ([HUMAN_HANDOFF.md](docs/HUMAN_HANDOFF.md)), then `make competition-audit`.
2. Fix every INCOMPATIBLE finding against `sample_submission`; re-check UNVERIFIED rows.
3. First real task: `make baseline` (B0, clean tree) and run that archive on ONE task.
4. Smoke (5–10 deterministic dev tasks), then B0 baseline on DEV, then failure analysis.
5. Only then B1→B5, FULL and ablations, each compared to B0 on the same tasks.
6. Budget calibration, held-out freeze, LoRA only if the gate in `docs/FINAL_VARIANT_DECISION.md` is met.
7. Paper from generated tables; release candidate; Kaggle upload (deadline 2026-12-02; paper 2026-11-12).

## License

MIT; see [LICENSE](LICENSE).
