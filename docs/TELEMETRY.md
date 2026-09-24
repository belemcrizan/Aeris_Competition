# Telemetry

Schema and validation: `aeris_comp/telemetry.py`. Every event is one JSON object per line with exactly these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `timestamp` | number | Unix seconds |
| `task_id` | string or null | Task instance id. Skills read `AERIS_TASK_ID`; when it is unset, `read_events(..., task_id=...)` fills it in after the run |
| `variant` | string or null | Variant id (`AERIS_VARIANT`, filled the same way) |
| `event_type` | string | One of the 20 types below |
| `duration` | number or null | Seconds, when the emitter measured it |
| `tool` | string or null | Emitter, for example `skill:testing` or `local_scorer` |
| `success` | bool or null | Outcome, when one exists |
| `metadata` | object | Event-specific data |

Inside the sandbox, skills append events to `$AERIS_STATE_DIR/events.jsonl`, which defaults to `/tmp/aeris` and is never inside `/workspace`. The local scorer writes `artifacts/runs/<run>/events.jsonl`.

## Event types and who emits them

| Event | Source today | Metadata |
| --- | --- | --- |
| `task_start`, `task_end` | Harness trace (BLOCKED: format unknown) | |
| `tool_call` | Harness trace (BLOCKED) | |
| `tool_result` | Harness trace (BLOCKED); `skill:ledger` for recorded experiments | `kind`, `command`, `purpose`; `error_code` when a tool reports one |
| `semantic_search`, `graph_expansion`, `file_read`, `edit` | Harness trace (BLOCKED) | |
| `hypothesis_created`, `hypothesis_updated` | `skill:ledger` | `id`, `target`, `weight`, `rejected` |
| `uncertainty_state` | `skill:ledger status` | `level`, `entropy`, `top`, `top_p`, `n_hypotheses`, `action` |
| `budget_status` | `skill:ledger status` | `mode`, `budget_used` |
| `patch_attempt` | `skill:ledger patch` | `files`, `hypothesis`, `result`, `attempt` |
| `test_start`, `test_result` | `skill:testing` | `args`, `timeout`; `status`, `counts` |
| `failure_signature` | `skill:testing` (every non-PASS run) | `signature`, `status`, `seen`, `repeated` |
| `retry` | `skill:testing` (a signature seen again) | `signature`, `seen` |
| `review` | `skill:review` | `files`, `added`, `removed`, `flags` |
| `submit_patch` | Harness trace (BLOCKED) | |
| `grade_result` | `run_experiment.py score` | `status`, `failure_category` |

Harness-only events need the harness trace format (gap E-05). Until it is known, localization metrics, which need `file_read` order, cannot be computed from real runs.

## Using events

- `read_events(path)` validates every line and reports the file and line number of the first bad one.
- `suggest_labels(events, scorer_status)` proposes failure labels (`REPEATED_FAILURE`, `PREMATURE_PATCH`, `GRAPH_EXPLOSION`, `TOOL_SCHEMA_FAILURE`, `NO_PATCH`, `BUDGET_EXHAUSTION`). A human confirms them during trace review; they are never used as ground truth on their own.
- The thresholds in `suggest_labels` may be tuned on the dev split only.
