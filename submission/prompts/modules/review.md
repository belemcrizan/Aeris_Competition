# Review before submitting

Immediately before submit_patch, run the review skill script review_diff.py. It inspects git status and git diff HEAD and flags scratch or generated files, modified test files, dependency file changes, debugging statements, whitespace-only changes and unusually large diffs.

Resolve every flag or confirm it is intended, then answer these questions from the diff:

- Does every changed line contribute to the fix described in the issue?
- Is any existing behavior changed that the issue did not ask for?
- Are public signatures and interfaces preserved, and are all call sites of any changed function still valid?
- Is the whole issue addressed, including every case or parameter it mentions?

Undo unrelated edits with edit_file, delete scratch files you created in /workspace, run the targeted tests one final time if you changed code, then call submit_patch.
