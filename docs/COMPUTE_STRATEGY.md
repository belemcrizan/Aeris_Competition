# Compute strategy

The competition harness is authoritative for everything that is scored. Other compute only prepares or analyses; it never becomes part of the submitted agent.

| Where | Responsible for | Never |
| --- | --- | --- |
| **LOCAL** (this repository, CI) | Lint, tests, building and validating every variant, ADK conformance, the release manifest, scoring predictions with the local scorer, metrics, tables, figures, docs | Claiming a harness result; running held-out tuning |
| **KAGGLE / HARNESS** | Running the agent with `gemma-4-31b-it-qat-w4a16-ct` on real tasks; official PASS/FAIL; the traces the analysis uses; accepting `submission.zip` | Being replaced by a local or cloud imitation for any reported number |
| **GCP (optional)** | Only if a measured need appears: LoRA training (after the gate in `docs/FINAL_VARIANT_DECISION.md`), large offline metric processing, artifact storage | Hosting or serving the competition agent; adding Vertex AI, Cloud Run or any network service to the submission |

## Rules

- The submitted agent has no network access and no dependency outside the archive and the harness tools. The validator's blocking POLICY checks (`CODE_REFERENCE`, `FORBIDDEN_FILE`, `POSSIBLE_SECRET`) enforce the code and credential side of this.
- GCP is used only after a written, measured justification (for example, LoRA training that meets the gate), recorded in this file with its dates and costs.
- No credential for any of these environments lives in the repository (`docs/HUMAN_HANDOFF.md`).

## Current state

LOCAL is complete and green in CI. KAGGLE/HARNESS is blocked on human access (`docs/STATUS.md`). GCP is unused: no measured need exists.
