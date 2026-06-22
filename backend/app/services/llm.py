"""
LLM service — the single entry point every agent uses to call Groq.

Wraps the OpenAI-compatible SDK pointed at Groq's endpoint. All 16 LangGraph
agents call call_llm() rather than touching the Groq client directly, so
fallback behavior, JSON mode, and error handling stay consistent everywhere.
"""
import json
import logging
from functools import lru_cache
from typing import Optional

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from app.config import settings

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Only genuinely transient failures are retried against the fallback model.
# NOTE: every openai-sdk status error (BadRequestError, AuthenticationError,
# RateLimitError, InternalServerError, ...) inherits from APIError, so
# catching APIError itself would also retry on 400s/401s — failures a
# different model can't fix. List the specific transient classes instead.
_RETRYABLE_ERRORS = (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError)


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    """Builds a single OpenAI-compatible client pointed at Groq, reused
    across calls within this process."""
    if not settings.GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to your .env file before "
            "calling the LLM service."
        )
    return OpenAI(api_key=settings.GROQ_API_KEY, base_url=GROQ_BASE_URL)


def call_llm(
    prompt: str,
    system: Optional[str] = None,
    json_mode: bool = False,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
) -> str:
    """Call Groq's chat completion endpoint with automatic fallback.

    Tries settings.GROQ_MODEL first; on a retryable failure (timeout, rate
    limit, transient API error), retries once against
    settings.GROQ_FALLBACK_MODEL. Non-retryable errors (bad request, auth)
    raise immediately without wasting a fallback attempt.

    Args:
        prompt: the user-turn content.
        system: optional system prompt setting agent behavior/persona.
        json_mode: if True, asks Groq to return a raw JSON object (no
            markdown fences) and sets response_format accordingly. The
            caller is still responsible for json.loads()-ing the result.
        temperature: sampling temperature, defaults to a low value suited
            to consistent, structured agent outputs.
        max_tokens: optional cap on the response length.

    Returns:
        The assistant's response content as a string.

    Raises:
        RuntimeError: if both the primary and fallback model calls fail.
    """
    if not prompt or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    client = get_client()

    messages = []
    if system:
        if json_mode and "json" not in system.lower():
            # Groq's json_object mode requires the word "json" to appear
            # somewhere in the prompt messages, or the API rejects the call.
            system = f"{system}\n\nRespond only with a valid JSON object."
        messages.append({"role": "system", "content": system})
    elif json_mode:
        messages.append({"role": "system", "content": "Respond only with a valid JSON object."})
    messages.append({"role": "user", "content": prompt})

    kwargs = {
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(model=settings.GROQ_MODEL, **kwargs)
        return response.choices[0].message.content
    except _RETRYABLE_ERRORS as primary_error:
        logger.warning(
            "Primary model '%s' failed (%s), retrying with fallback '%s'",
            settings.GROQ_MODEL, type(primary_error).__name__, settings.GROQ_FALLBACK_MODEL,
        )
        try:
            response = client.chat.completions.create(model=settings.GROQ_FALLBACK_MODEL, **kwargs)
            return response.choices[0].message.content
        except _RETRYABLE_ERRORS as fallback_error:
            raise RuntimeError(
                f"LLM call failed on both primary model '{settings.GROQ_MODEL}' "
                f"({type(primary_error).__name__}: {primary_error}) and fallback "
                f"model '{settings.GROQ_FALLBACK_MODEL}' "
                f"({type(fallback_error).__name__}: {fallback_error})"
            ) from fallback_error


def call_llm_json(
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
) -> dict:
    """Convenience wrapper around call_llm(json_mode=True) that also parses
    the result. Raises RuntimeError with the raw response included if Groq
    returns something that isn't valid JSON, since silently returning a
    string would just move the bug to whoever consumes this."""
    raw = call_llm(prompt, system=system, json_mode=True, temperature=temperature, max_tokens=max_tokens)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"LLM response was not valid JSON despite json_mode=True. "
            f"Raw response: {raw[:500]!r}"
        ) from e
