# Testing

Every test carries exactly one level marker, applied in `tests/conftest.py`:

| Level | Marker | What it covers | Where it runs |
| --- | --- | --- | --- |
| UNIT | `unit` | Pure Python: validator, taxonomy, telemetry schema, metrics, split, ledger logic | Everywhere; `make test-unit` |
| LOCAL_INTEGRATION | `local_integration` | Spawns git or pytest, builds archives, runs skill scripts against temporary repositories, runs ADK's own parser or wrapper code | Everywhere; `make test-integration`. ADK tests skip without `google-adk` |
| OFFICIAL_HARNESS | `official_harness` | Needs the competition harness, model and dataset | Always skipped until the harness is available (gap C-03) |

`make test` runs all of them. CI runs UNIT and LOCAL_INTEGRATION in the `check` job, plus a separate `adk-conformance` job that installs `google-adk==2.9.2`.

A passing local test is evidence at our own authority level (7), or level 6 for the ADK-backed tests. It is never evidence that the harness behaves the same way: harness evidence is recorded only as HARNESS_TESTED in [GAP_CLOSURE.md](GAP_CLOSURE.md).

Test isolation: an autouse fixture points `AERIS_STATE_DIR` at a per-test temporary directory, so skill scripts never write to a real `/tmp/aeris`. `sys.dont_write_bytecode` keeps `__pycache__` out of `submission/`.
