"""Competition facts used by the builder and validator.

Every value here is traced to a source in docs/COMPETITION_REQUIREMENTS.md.
"""

from __future__ import annotations

# Source: competition Overview > "Model Selection and LoRA Adapters" (R-MODEL-1).
ALLOWED_MODELS = frozenset({"gemma-4-31b-it-qat-w4a16-ct"})

# Source: competition Overview > "The predefined tools available to your agent" (R-TOOLS-1).
HARNESS_TOOLS = frozenset(
    {
        "run_command",
        "submit_patch",
        "get_status",
        "read_file",
        "edit_file",
        "write_file",
        "get_code_neighbors",
        "search_similar_code",
        "get_code_subgraph",
    }
)

# Source: "custom subagents defined via agent_tool" (competition) and the generic ADK
# ToolConfig docstring, which names the built-in class ``AgentTool``. Which spelling the
# harness accepts is UNVERIFIED (R-TOOLS-2), so both are accepted with a warning for the
# lowercase form.
AGENT_TOOL_NAMES = frozenset({"AgentTool", "agent_tool"})

# Generic ADK LlmAgentConfig fields (adk-python config_schemas/AgentConfig.json) minus
# everything that references Python code, plus the competition-specific ``adapter`` field.
LLM_AGENT_KEYS = frozenset(
    {
        "agent_class",
        "name",
        "model",
        "description",
        "instruction",
        "static_instruction",
        "tools",
        "sub_agents",
        "generate_content_config",
        "include_contents",
        "output_key",
        "disallow_transfer_to_parent",
        "disallow_transfer_to_peers",
        "adapter",
    }
)

# Fields that make ADK import Python code. The competition forbids code execution outside
# the sandbox (R-SANDBOX-2), so these are rejected.
CODE_REFERENCE_KEYS = frozenset(
    {
        "before_agent_callbacks",
        "after_agent_callbacks",
        "before_model_callbacks",
        "after_model_callbacks",
        "before_tool_callbacks",
        "after_tool_callbacks",
        "model_code",
        "input_schema",
        "output_schema",
        "code",
    }
)

WORKFLOW_AGENT_KEYS = frozenset({"agent_class", "name", "description", "sub_agents", "max_iterations"})
WORKFLOW_AGENT_CLASSES = frozenset({"SequentialAgent", "ParallelAgent", "LoopAgent"})

# google.genai GenerateContentConfig accepts both snake_case and camelCase field names.
GENERATE_CONTENT_KEYS = frozenset(
    {
        "temperature",
        "top_p",
        "topP",
        "top_k",
        "topK",
        "max_output_tokens",
        "maxOutputTokens",
        "stop_sequences",
        "stopSequences",
        "presence_penalty",
        "presencePenalty",
        "frequency_penalty",
        "frequencyPenalty",
        "seed",
        "candidate_count",
        "candidateCount",
    }
)

ADAPTER_REQUIRED_FILES = ("adapter_config.json", "adapter_model.safetensors")

ROOT_ENTRIES = frozenset({"agent.yaml", "configs", "prompts", "sub_agents", "adapters", "skills", "tools"})
