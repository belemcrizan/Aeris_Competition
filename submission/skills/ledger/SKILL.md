---
name: ledger
description: Compact evidence ledger for one task. Tracks issue claims, competing root-cause hypotheses with confidence weights, experiments and patch attempts, and reports entropy-based uncertainty and a budget-aware recommended action.
---

# ledger

State lives in /tmp/aeris/ledger.json (never in /workspace). One task per sandbox, so no reset is needed; `ledger.py reset` clears it.

## Commands (script: scripts/ledger.py)

- `claim "text"`: record a fact extracted from the issue.
- `add H1 --target sym --weight 0.5 --claim "mechanism"`: add a hypothesis.
- `update H1 [--weight W] [--for "evidence"] [--against "evidence"] [--reject]`: update one.
- `experiment --command "cmd" --result "outcome" [--purpose "why"]`: record an investigation step.
- `patch --files a.py,b.py --hypothesis H1 --result pass|fail|untested [--note "why"]`: record an attempt.
- `status [--budget-used 0.4]`: print the ledger, normalized weights, entropy, uncertainty level, budget mode and recommended action.

## Output

Every command prints the compact ledger. `status` adds lines such as:

```
MODE: NORMAL  UNCERTAINTY: MEDIUM  top=H1 p=0.55 entropy=0.62
ACTION: DISCRIMINATE H1 vs H2 with the cheapest check whose outcome differs
```

Weights are confidence weights, not calibrated probabilities.
