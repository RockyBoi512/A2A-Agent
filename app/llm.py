# ══════════════════════════════════════════════════════════════════════════
#  LLM Configuration — LiteLLM gateway to SAP AI Core
# ══════════════════════════════════════════════════════════════════════════

import os
import litellm

# Configure LiteLLM for SAP AI Core
AICORE_MODEL = os.getenv("AICORE_MODEL", "anthropic--claude-4.6-sonnet")

# LiteLLM reads these env vars automatically for sap_ai_core provider:
#   AICORE_CLIENT_ID, AICORE_CLIENT_SECRET, AICORE_AUTH_URL,
#   AICORE_BASE_URL, AICORE_RESOURCE_GROUP

# Suppress verbose logging
litellm.suppress_debug_info = True


def get_model_name() -> str:
    """Return the full LiteLLM model identifier for SAP AI Core."""
    return f"sap_ai_core/{AICORE_MODEL}"


def call_llm(messages: list[dict], temperature: float = 0.4, max_tokens: int = 2000) -> str:
    """Call LLM via LiteLLM → SAP AI Core."""
    try:
        response = litellm.completion(
            model=get_model_name(),
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[LLM unavailable: {str(e)}]"
