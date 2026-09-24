# Competing hypotheses and the evidence ledger

Before editing, keep one to three competing root-cause hypotheses. Each names a target symbol or file and a concrete mechanism, for example: H1 target package.routing.serialize, the exclude flag is dropped when the value is a list.

Record them with the ledger skill script ledger.py; it stores a compact state file in /tmp and prints the current ledger:

- ledger.py claim "one-line fact extracted from the issue"
- ledger.py add H1 --target package.module.func --weight 0.5 --claim "mechanism"
- ledger.py update H1 --weight 0.7 --for "evidence supporting H1"
- ledger.py update H2 --weight 0.1 --against "evidence contradicting H2"
- ledger.py experiment --command "what you ran" --result "one-line outcome"
- ledger.py patch --files path/a.py --hypothesis H1 --result fail --note "one-line reason"
- ledger.py status

Rules:

- Weights are your confidence, not calibrated probabilities. The script normalizes them.
- Update weights after every piece of evidence: reading code, a reproduction result, a test failure. Evidence is one line; never paste raw output into the ledger.
- Actively look for evidence that could refute your leading hypothesis, not only evidence that supports it.
- If new evidence fits no hypothesis, add a new one instead of forcing it into an existing one.
