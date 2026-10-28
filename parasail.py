"""The model, on Parasail.

Vendored into both Halloween templates. Keep the copies identical;
templates/check.sh compares them.

Parasail is not a platform on One. It is where the model runs: an
OpenAI-compatible API at https://api.parasail.io/v1. CrewAI talks to it
through `crew_llm()`, plain Python through `complete_json()`. One stays the
way every agent acts on an app.

The model must support tool (function) calling, because CrewAI agents call
tools. List what your key can use:

    curl -s https://api.parasail.io/v1/models -H "Authorization: Bearer $PARASAIL_API_KEY" | jq -r '.data[].id'
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

BASE_URL = "https://api.parasail.io/v1"
DEFAULT_MODEL = "parasail-kimi-k26"
# Other tool-calling models Parasail lists at the time of writing. Model ids change; check /v1/models.
TOOL_CALLING_CANDIDATES = ("parasail-kimi-k26", "parasail-deepseek-v4-flash", "parasail-qwen3p6-35b-a3b", "parasail-glm-52")


class ParasailError(RuntimeError):
    """A Parasail call or check failed. The message never contains the key."""


def model_id() -> str:
    return (os.environ.get("PARASAIL_MODEL") or DEFAULT_MODEL).strip()


def api_key() -> str:
    key = (os.environ.get("PARASAIL_API_KEY") or "").strip()
    if not key:
        raise ParasailError("PARASAIL_API_KEY is empty. Get a key at https://www.saas.parasail.io/keys and put it in .env")
    return key


def base_url() -> str:
    return (os.environ.get("PARASAIL_BASE_URL") or BASE_URL).rstrip("/")


def _redact(text: object) -> str:
    out = str(text)
    key = (os.environ.get("PARASAIL_API_KEY") or "").strip()
    if len(key) >= 8:
        out = out.replace(key, "<redacted>")
    return out


def list_models(timeout: int = 20) -> list[str]:
    """Model ids this key can use, from GET /v1/models."""
    req = urllib.request.Request(f"{base_url()}/models", headers={"Authorization": f"Bearer {api_key()}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = json.loads(res.read().decode())
    except urllib.error.HTTPError as exc:
        raise ParasailError(f"Parasail /models answered {exc.code}. Check PARASAIL_API_KEY") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ParasailError(f"could not reach Parasail at {base_url()}: {_redact(exc)}") from exc
    return sorted(m.get("id", "") for m in body.get("data", []) if m.get("id"))


def check_model() -> str:
    """Fail early, with the list to pick from, when PARASAIL_MODEL is not served for this key."""
    wanted = model_id()
    ids = list_models()
    if wanted not in ids:
        hint = [m for m in TOOL_CALLING_CANDIDATES if m in ids] or ids[:10]
        raise ParasailError(f"PARASAIL_MODEL={wanted} is not in your Parasail models. Pick one that supports tool calling, "
                            f"for example: {', '.join(hint) or 'none listed'}")
    return wanted


def crew_llm(temperature: float = 0.2, **kwargs):
    """A CrewAI LLM on Parasail, through CrewAI's native OpenAI-compatible client.

    `provider="openai"` with the bare model id, not `model="openai/<id>"`: in crewai 1.15.2 the
    prefix form only reaches the native client for model names CrewAI already knows (gpt-4o and
    friends). Any other name falls through to LiteLLM, which plain `crewai` does not install, and
    the constructor raises ImportError. With the prefix and `provider` together, the prefix is
    sent to Parasail as part of the model name.

    `context_window_size` tells CrewAI when to summarise a long conversation. It defaults to
    about 7k tokens for a model it does not know, which is far below what Parasail's models take.
    """
    from crewai import LLM

    window = int(os.environ.get("PARASAIL_CONTEXT_WINDOW") or 128000)
    llm = LLM(model=model_id(), provider="openai", base_url=base_url(), api_key=api_key(),
              temperature=temperature, **kwargs)
    # The native client reads its window from a table of OpenAI model names; pin ours instead.
    object.__setattr__(llm, "get_context_window_size", lambda: int(window * 0.85))
    return llm


def client():
    from openai import OpenAI

    return OpenAI(base_url=base_url(), api_key=api_key())


def complete_json(system: str, user: str, max_tokens: int = 4000, temperature: float = 0.2) -> dict:
    """One chat completion that must come back as a JSON object (`response_format` json_object)."""
    try:
        res = client().chat.completions.create(
            model=model_id(),
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
    except Exception as exc:  # noqa: BLE001 - the SDK raises many types; the caller only needs a clean message
        raise ParasailError(f"Parasail chat completion failed: {_redact(exc)[:300]}") from exc
    return parse_json(res.choices[0].message.content or "")


def parse_json(text: str) -> dict:
    """Parse a JSON object out of a reply, tolerating a ```json fence or text around it."""
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ParasailError(f"the model did not return JSON: {text[:200]!r}") from None
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ParasailError(f"the model returned broken JSON: {text[:200]!r}") from exc
    if not isinstance(value, dict):
        raise ParasailError(f"expected a JSON object, got {type(value).__name__}")
    return value
