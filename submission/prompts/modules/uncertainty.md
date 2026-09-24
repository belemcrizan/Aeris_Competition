# Uncertainty gate

Before the first edit and after every failed patch, run ledger.py status. Pass the fraction of budget used when you know it from get_status, for example ledger.py status --budget-used 0.35. The script prints the budget mode (NORMAL, CONSERVATIVE, CRITICAL), the normalized entropy of your hypothesis weights, the uncertainty level and a recommended action.

- HIGH uncertainty: do not edit source files. Gather evidence that separates hypotheses: read the code of the top candidates, run a reproduction.
- MEDIUM uncertainty: run the single cheapest check whose outcome differs between the top two hypotheses, update weights, then decide again.
- LOW uncertainty: write the minimal patch for the leading hypothesis.

Budget pressure lowers the bar. In CONSERVATIVE mode only targeted reads and tests are allowed. In CRITICAL mode stop exploring, patch the leading hypothesis if there is no patch yet, validate it once and submit.

The gate never justifies endless exploration: after eight investigation steps without reaching LOW, patch the leading hypothesis anyway and let the tests provide the next evidence.
