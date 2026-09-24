---
name: testing
description: Run targeted pytest commands and turn the output into a compact failure report with a stable failure signature, so repeated failures are detected and test results can be used as evidence.
---

# testing

## Script: scripts/run_tests.py

Arguments are passed to pytest, for example `tests/test_routing.py -k exclude`. Optional flags placed before the pytest arguments:

- `--timeout SECONDS` (default 300): kill pytest after this many seconds.
- `--repo PATH` (default /workspace, or the current directory if it does not exist).

pytest runs with `-q -rfE --tb=short -p no:cacheprovider` and `PYTHONDONTWRITEBYTECODE=1`, so nothing is written into the repository.

## Output

```
RESULT: FAIL  passed=12 failed=1 errors=0 skipped=0  (4.1s)
FAILED tests/test_routing.py::test_exclude_unset - AssertionError: assert {'a': 1} == {}
  first comparison: {'a': 1} == {}
  first exception: AssertionError: assert {'a': 1} == {}
  frames: tests/test_routing.py:40 test_exclude_unset | fastapi/routing.py:112 serialize_response
SIGNATURE: 3f2a9c1d0b7e  (seen 2 times for these arguments: REPEATED)
```

A repeated signature means the last change did not affect the failure. History is kept in /tmp/aeris/test_history.json.
