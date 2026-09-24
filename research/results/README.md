# Results

Not yet measured. No run of the agent against the competition harness has been performed, because the harness, the dataset and a Gemma 4 endpoint are not available ([docs/STATUS.md](../../docs/STATUS.md)).

Files that will appear here, and what blocks each one:

| File | Produced by | Blocked by |
| --- | --- | --- |
| `data_split.json` | `python scripts/make_split.py --tasks <tasks.jsonl>` | Dataset (gap X-04) |
| `FIRST_PASS.md` | First harness run with a PASS | Harness (X-01, X-02) |
| `smoke_b0.json`, `smoke_b0.md` | `run_experiment.py score` + `summarize` on a small B0 run | Harness (X-03) |
| Per-run `manifest.json`, `summary.json`, link to `records.jsonl` and `events.jsonl` | `run_experiment.py prepare` / `score` | Harness (X-06) |

None of these files is created by hand, and no placeholder numbers are committed. Negative and aborted runs are kept too.
