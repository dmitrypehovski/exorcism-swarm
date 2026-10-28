"""You.com grounding, on You.com's own key and endpoint.

The Analyst's web tool calls the Search API directly:

    POST https://ydc-index.io/v1/search      header: X-API-Key

It is deliberately *not* relayed through another partner's passthrough. The rubric counts a
partner used only as a passthrough as unused, so You.com is used as You.com and One is used for
what only One does: delivering the order into a real app (see dispatch.py).

One key, one endpoint. `count` is capped at 10 because a tick needs a couple of sentences, not a
page; snippets keep the swarm's context small enough to think in.
"""
import json
import os
import urllib.error
import urllib.request

from crewai.tools import tool

ENDPOINT = os.environ.get("YOUCOM_SEARCH_URL", "https://ydc-index.io/v1/search")
DEFAULT_COUNT = 3


class YouComError(RuntimeError):
    """Raised when You.com cannot answer, so the caller can fall back on the sensors alone."""


def _key() -> str:
    key = os.environ.get("YDC_API_KEY", "").strip()
    if not key:
        raise YouComError("YDC_API_KEY is empty in .env")
    return key


def search(query: str, count: int = DEFAULT_COUNT, timeout: int = 25) -> list:
    """Return [{title, url, snippet}] for a natural-language query. Raises YouComError."""
    body = json.dumps({"query": query, "count": max(1, min(int(count), 10))}).encode()
    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"X-API-Key": _key(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:200].decode(errors="replace")
        raise YouComError(f"You.com search failed: HTTP {exc.code} {detail}") from None
    except urllib.error.URLError as exc:
        raise YouComError(f"You.com unreachable: {exc.reason}") from None

    hits = (data.get("results") or {}).get("web") or data.get("web") or []
    out = []
    for hit in hits[: max(1, int(count))]:
        snips = hit.get("snippets") or hit.get("highlights") or []
        if isinstance(snips, str):
            snips = [snips]
        out.append({
            "title": hit.get("title", ""),
            "url": hit.get("url", ""),
            "snippet": " ".join(snips)[:400],
        })
    return out


def format_hits(hits: list) -> str:
    if not hits:
        return "no results"
    return "\n".join(f"- {h['title']} — {h['url']}\n  {h['snippet']}" for h in hits)


@tool("youcom_search")
def youcom_search(query: str, count: int = DEFAULT_COUNT) -> str:
    """Search the live web with the You.com Search API. Returns titles, URLs and snippets.

    Use it to test a mundane explanation for a sighting (HVAC work, a party, a fog machine,
    wiring, a costume) or to confirm that an anomaly is being reported outside the building.
    """
    try:
        return format_hits(search(query, count))
    except YouComError as exc:
        return f"You.com search unavailable ({exc}); decide from the sensors and witnesses alone."


def youcom_tools() -> list:
    """The tool list handed to the Analyst when a You.com key is present."""
    return [youcom_search] if os.environ.get("YDC_API_KEY", "").strip() else []
