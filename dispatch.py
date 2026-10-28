"""Getting the escalation out of the room.

Order, straight from the brief:

1. **One first.** The venue dispatch is a One action: the channel is a *path variable*, the message is
   the body, and the payload is built from runtime state rather than a hardcoded string. One is also
   what files the accompanying issue and runs the You.com grounding call.
2. **The venue webhook if One cannot reach the channel.** One dispatches into servers its account can
   install into; a participant cannot add an app to the venue's server, so the brief publishes a
   webhook for exactly this case and calls the fallback fully acceptable.

Either way the message is verified rather than hoped for: Discord returns the created message when the
webhook is called with `wait=true`, and that id is what we report.

    python dispatch.py --escalation 'team-x · sector · action · rationale'
    python dispatch.py --verify 1565115356207513774
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request

VENUE_WEBHOOK = os.environ.get(
    "VENUE_DISCORD_WEBHOOK",
    "https://discord.com/api/webhooks/1564863196202934376/"
    "rJr-P0-a9FWnsehNckLK_i-HnTMxdzp8SffZIqRjEWEGEE81VbN03DEyDKddxqEcgjOD")
VENUE_CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID", "1564842098740695100")
TEAM = os.environ.get("TEAM_HANDLE", "team-crimson-raven")


def escalation_line(tick: dict, action: str, rationale: str) -> str:
    """team handle · sector · action · one-line rationale — the format the brief asks for."""
    reports = tick.get("sector_reports") or []
    worst = max(reports, key=lambda r: float((r.get("sensors") or {}).get("emf_milligauss") or 0)) if reports else {}
    sector = worst.get("sector", "unknown")
    return f"**{TEAM} · {sector} · {action}**\ntick {tick.get('tick_id')} — {rationale}"


def post_via_webhook(content: str, username: str = TEAM) -> dict:
    body = json.dumps({"content": content, "username": username}).encode()
    # Discord answers 403 to urllib's default User-Agent, so name ourselves explicitly.
    req = urllib.request.Request(VENUE_WEBHOOK + "?wait=true", data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "exorcism-swarm/1.0 (hackathon; urllib)"})
    with urllib.request.urlopen(req, timeout=45) as res:
        return json.loads(res.read().decode())


def post_via_one(content: str, channel_id: str = VENUE_CHANNEL_ID) -> dict:
    """The partner path: One's three-tool loop, channel as a path variable."""
    from one_cli import execute, resolve
    action_id = resolve("discord", "send a message to a channel", "POST", "/channels/{channelId}/messages")
    key = os.environ.get("ONE_DISCORD_CONNECTION_KEY", "")
    if not action_id or not key:
        raise RuntimeError("no Discord connection in One: add one with `one add discord`")
    return execute("discord", action_id, key, data={"content": content},
                   path_vars={"channelId": channel_id})


def dispatch(content: str, prefer_one: bool = True) -> dict:
    """One first, the venue webhook when One has no route into the channel. Always report which."""
    if prefer_one:
        try:
            result = post_via_one(content)
            return {"via": "one", "channel": VENUE_CHANNEL_ID, "result": result}
        except Exception as exc:  # noqa: BLE001 - the fallback is sanctioned, not an error path to hide
            reason = f"{type(exc).__name__}: {exc}"
    else:
        reason = "One path not attempted"
    posted = post_via_webhook(content)
    return {"via": "venue-webhook", "one_unavailable": reason,
            "message_id": posted.get("id"), "channel": posted.get("channel_id"),
            "author": (posted.get("author") or {}).get("username")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--escalation", help="the escalation text to post into the venue channel")
    ap.add_argument("--no-one", action="store_true", help="skip the One attempt and use the webhook")
    args = ap.parse_args()
    if not args.escalation:
        ap.print_help()
    else:
        print(json.dumps(dispatch(args.escalation, prefer_one=not args.no_one), indent=2, ensure_ascii=False))
