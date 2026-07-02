"""LLM provider 抽象:优先 Anthropic(Claude),其次 OpenAI(GPT),都没有则不可用。

两个能力:
- tool_call:强制结构化输出(JD 解析用)
- complete_text:短文本生成(打分理由润色用)
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
    """强制一次结构化工具调用,返回 (参数 dict, 使用的模型)。无 provider 抛 RuntimeError。"""
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
    """短文本生成,返回 (文本, 模型);无 provider 或失败返回 None(调用方降级)。"""
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
    except Exception as e:  # 网络/额度问题一律降级
        logger.warning("LLM text completion failed: %s", e)
    return None
