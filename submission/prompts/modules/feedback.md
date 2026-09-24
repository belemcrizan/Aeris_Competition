# Test failures are evidence

Run tests through the testing skill script run_tests.py, passing pytest arguments, for example run_tests.py tests/test_routing.py -k exclude. It runs pytest with a timeout and prints a compact result: counts, failing test ids, exception types, expected versus actual values, the source frames involved and a failure signature. It also reports when the same signature was already seen.

Run the targeted tests once before editing when you need a baseline, so you can tell pre-existing failures from failures you caused.

After a failing run, interpret before editing again:

- Is the failure in the behavior you changed, in a test that already failed at baseline, or in an unrelated place you broke?
- Did the error change? A new error means progress or a new regression; the same signature means your hypothesis or your patch is wrong.
- Which hypotheses does the failure strengthen or weaken? Update the ledger when it is enabled.

Retry rules:

- A repeated failure signature means do not make another variation of the same patch. Re-examine the code path and consider the next hypothesis.
- At most three substantially different patch attempts per task. After that keep the attempt with the best test outcome, make sure the code is in that state, and submit.
- Never delete, skip or weaken tests to make them pass.
