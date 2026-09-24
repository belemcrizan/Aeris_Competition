# LoRA adapters

No adapter is used. Phase 1 (the current phase) runs the base model only.

## Layout (verified competition format)

```
adapters/<adapter_name>/
├── adapter_config.json          # PEFT config, peft_type LORA, base gemma-4-31b-it(-qat)
└── adapter_model.safetensors
```

A variant enables an adapter with `adapter: <adapter_name>` in its `experiments/configs/*.yaml`. The build copies only the two files above into the archive and adds `adapter: <adapter_name>` to the agent. The validator checks the files, the JSON, the `peft_type` and the safetensors header.

Adapter weights are git-ignored. Store them outside git (or with Git LFS) and record their SHA-256 here.

## When an adapter is justified

Only after baseline measurements show a frequent, learnable failure category that a prompt change did not fix (see `research/methodology.md`, "Fine-tuning gate").

## Required record for any adapter

| Field | Value |
| --- | --- |
| Base model | |
| Training data provenance | |
| Preprocessing | |
| Excluded repositories and tasks (contamination control) | |
| Hyperparameters (r, alpha, dropout, target modules, lr, steps, sequence length) | |
| Seeds | |
| Training compute | |
| Evaluation split | |
| SHA-256 of `adapter_model.safetensors` | |

Never evaluate on training examples.
