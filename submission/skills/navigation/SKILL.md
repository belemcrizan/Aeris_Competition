---
name: navigation
description: Map fully qualified graph node ids (package.module.Class.method) to file paths and line ranges, and find the test files that exercise given source files or symbols.
---

# navigation

Both scripts are read-only and default to the repository at /workspace (or the current directory if it does not exist); pass `--repo PATH` first to override.

## Script: scripts/locate_symbol.py

Arguments: one or more node ids, for example `fastapi.routing.APIRoute.get_route_handler`.

```
fastapi.routing.APIRoute.get_route_handler -> fastapi/routing.py:512-540  def get_route_handler(self) -> Callable:
```

The range can be passed straight to read_file. When the module cannot be resolved, the script falls back to a bounded search for `def name` / `class name` and prints up to five candidates.

## Script: scripts/find_tests.py

Arguments: source file paths, dotted symbols or bare names, for example `fastapi/routing.py serialize_response`.

```
tests/test_serialize_response.py score=9 (imports fastapi.routing; mentions serialize_response x3)
SUGGESTED: python -m pytest -x -q tests/test_serialize_response.py tests/test_response_model.py
```
