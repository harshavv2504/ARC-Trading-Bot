"""
Unified LLM client — auto-selects OpenAI or Anthropic based on which key is set.
OpenAI takes priority if both keys are present.

Two model tiers:
  day    → ai_model_day    (gpt-4.1)      smarter, runs once/day
  signal → ai_model_signal (gpt-4.1-mini) faster, runs every 5 min
"""

import json
import re
from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)

_client = None
_provider: str = ""


def _init():
    global _client, _provider
    if _client:
        return

    if settings.openai_api_key:
        from openai import OpenAI
        _client = OpenAI(api_key=settings.openai_api_key)
        _provider = "openai"
        logger.info(
            f"LLM provider: OpenAI | "
            f"day={settings.ai_model_day} | signal={settings.ai_model_signal}"
        )
    elif settings.anthropic_api_key:
        import anthropic
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        _provider = "anthropic"
        logger.info(
            f"LLM provider: Anthropic | "
            f"day={settings.ai_model_day} | signal={settings.ai_model_signal}"
        )
    else:
        logger.warning("No AI API key set — LLM calls will fail")


def chat(system: str, user: str, max_tokens: int = 512, model: str | None = None) -> str:
    """
    Send a system + user message, return the response text.
    Pass model explicitly or it defaults to ai_model_signal.
    """
    _init()

    if not _client:
        raise RuntimeError("No AI API key configured in .env")

    chosen_model = model or settings.ai_model_signal

    if _provider == "openai":
        # gpt-5.x series uses max_completion_tokens; gpt-4.x uses max_tokens
        token_kwarg = (
            {"max_completion_tokens": max_tokens}
            if chosen_model.startswith("gpt-5") or chosen_model.startswith("o")
            else {"max_tokens": max_tokens}
        )
        response = _client.chat.completions.create(
            model=chosen_model,
            **token_kwarg,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content.strip()

    elif _provider == "anthropic":
        response = _client.messages.create(
            model=chosen_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text.strip()

    raise RuntimeError(f"Unknown provider: {_provider}")


def chat_json(
    system: str,
    user: str,
    max_tokens: int = 512,
    model: str | None = None,
) -> dict:
    """Like chat() but parses and returns the JSON response as a dict."""
    raw = chat(system, user, max_tokens, model)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise


def provider() -> str:
    _init()
    return _provider
