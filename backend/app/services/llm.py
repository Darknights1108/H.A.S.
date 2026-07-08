"""LLM provider abstraction: Anthropic (Claude) preferred, OpenAI (GPT) as
fallback; unavailable when neither key is configured.

Two capabilities:
- tool_call: forced structured output (used for JD parsing)
- complete_text: short text generation (used to polish scoring reasoning)
"""

import json
import logging

from ..config import settings

logger = logging.getLogger(__name__)

ANTHROPIC_PARSE_MODEL = "claude-sonnet-4-6"
ANTHROPIC_TEXT_MODEL = "claude-haiku-4-5"
OPENAI_MODEL = "gpt-4o-mini"


def provider() -> str | None:
    if settings.anthropic_api_key:
        return "anthropic"
    if settings.openai_api_key:
        return "openai"
    return None


def tool_call(prompt: str, tool_name: str, description: str, schema: dict,
              max_tokens: int = 1500) -> tuple[dict, str]:
    """Force one structured tool call; returns (args dict, model used). Raises RuntimeError without a provider."""
    p = provider()
    if p == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model=ANTHROPIC_PARSE_MODEL,
            max_tokens=max_tokens,
            tools=[{"name": tool_name, "description": description, "input_schema": schema}],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": prompt}],
        )
        block = next(b for b in msg.content if b.type == "tool_use")
        return block.input, ANTHROPIC_PARSE_MODEL
    if p == "openai":
        import openai

        client = openai.OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=max_tokens,
            tools=[{
                "type": "function",
                "function": {"name": tool_name, "description": description, "parameters": schema},
            }],
            tool_choice={"type": "function", "function": {"name": tool_name}},
            messages=[{"role": "user", "content": prompt}],
        )
        call = resp.choices[0].message.tool_calls[0]
        return json.loads(call.function.arguments), OPENAI_MODEL
    raise RuntimeError("no LLM API key configured (ANTHROPIC_API_KEY or OPENAI_API_KEY)")


def complete_text(prompt: str, max_tokens: int = 300) -> tuple[str, str] | None:
    """Short text generation; returns (text, model), or None when no provider / on failure (caller degrades)."""
    p = provider()
    try:
        if p == "anthropic":
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            msg = client.messages.create(
                model=ANTHROPIC_TEXT_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text.strip(), ANTHROPIC_TEXT_MODEL
        if p == "openai":
            import openai

            client = openai.OpenAI(api_key=settings.openai_api_key)
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content.strip(), OPENAI_MODEL
    except Exception as e:  # degrade on any network/quota problem
        logger.warning("LLM text completion failed: %s", e)
    return None
