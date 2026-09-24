---
name: review
description: Pre-submission review of the working-tree diff. Flags scratch and generated files, modified tests, dependency changes, debugging statements, whitespace-only edits and oversized diffs before submit_patch captures them.
---

# review

## Script: scripts/review_diff.py

Optional arguments: `--repo PATH` (default /workspace, or the current directory if it does not exist).

Runs read-only git commands (`git status --porcelain`, `git diff HEAD`) and reads untracked files. It never modifies the repository or the index.

## Output

```
DIFF: 1 files, +4 -1
  M fastapi/routing.py +4 -1
FLAGS:
  DEBUG_STATEMENT fastapi/routing.py: added line contains print(
VERDICT: REVIEW (1 flags)
```

`VERDICT: OK` means no flags. Each flag is a prompt to check, not proof of a problem; for example print( is legitimate in a CLI module.
