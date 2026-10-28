"""Which model actually serves the swarm.

Parasail is the event's inference partner and stays the configured default. But a Parasail key
without a payment method lists models and then refuses every inference call with
`403 Inference not allowed`, which would stop the whole crew on its first thought.

So: probe Parasail once, before the run. If it answers, the swarm runs on Parasail. If it refuses,
fall back to OpenRouter so the facility still gets a supervised swarm, and say plainly in the trace
and on stdout which provider served the run. Nothing is hidden, and the Parasail path is a real code
path rather than a comment.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

PROBE = {"model": None, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}

_state: dict = {}


def _post(url: str, payload: dict, headers: dict, timeout: int = 25) -> tuple[bool, str]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={**headers, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            json.loads(res.read().decode())
        return True, "ok"
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:200].decode(errors="replace")
        return False, f"HTTP {exc.code}: {detail}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def _probe_parasail() -> tuple[bool, str]:
    key = (os.environ.get("PARASAIL_API_KEY") or "").strip()
    if not key:
        return False, "PARASAIL_API_KEY is empty"
    base = (os.environ.get("PARASAIL_BASE_URL") or "https://api.parasail.io/v1").rstrip("/")
    model = (os.environ.get("PARASAIL_MODEL") or "parasail-kimi-k26").strip()
    return _post(f"{base}/chat/completions", {**PROBE, "model": model},
                 {"Authorization": f"Bearer {key}"})


def _probe_openrouter() -> tuple[bool, str]:
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return False, "OPENROUTER_API_KEY is empty"
    base = (os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
    model = (os.environ.get("OPENROUTER_MODEL") or "deepseek/deepseek-v4.1-flash").strip()
    return _post(f"{base}/chat/completions", {**PROBE, "model": model},
                 {"Authorization": f"Bearer {key}"})


def resolve(force: str | None = None) -> dict:
    """Pick the provider once per run. Cached; the probe costs one token."""
    if _state and not force:
        return _state
    choice = {"provider": "parasail", "fallback": False, "reason": ""}
    ok, detail = _probe_parasail()
    if ok:
        choice["reason"] = "Parasail inference answered the probe"
    else:
        choice["parasail_error"] = detail
        ok2, detail2 = _probe_openrouter()
        if ok2:
            choice.update(provider="openrouter", fallback=True,
                          reason=f"Parasail refused inference ({detail[:120]}); OpenRouter answered the probe")
        else:
            choice.update(provider="none", reason=f"no provider answered: parasail={detail[:80]} openrouter={detail2[:80]}")
    _state.update(choice)
    return _state


def provider_note() -> str:
    c = resolve()
    model = (os.getenv("PARASAIL_MODEL") if c["provider"] == "parasail"
             else os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4.1-flash"))
    tag = "FALLBACK" if c["fallback"] else "primary"
    return f"{c['provider']} ({tag}) model={model} — {c['reason']}"


def crew_llm(temperature: float = 0.2, **kwargs):
    """A CrewAI LLM on whichever provider answered the probe."""
    from crewai import LLM

    c = resolve()
    window = int(os.environ.get("LLM_CONTEXT_WINDOW") or 128000)
    if c["provider"] == "parasail":
        import parasail
        return parasail.crew_llm(temperature=temperature, **kwargs)
    if c["provider"] == "openrouter":
        llm = LLM(model=os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4.1-flash"),
                  provider="openai",
                  base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                  api_key=os.environ["OPENROUTER_API_KEY"], temperature=temperature, **kwargs)
        object.__setattr__(llm, "get_context_window_size", lambda: int(window * 0.85))
        return llm
    raise RuntimeError(c["reason"])
