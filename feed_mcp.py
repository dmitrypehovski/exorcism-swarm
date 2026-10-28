"""The venue scenario feed: pull a tick, report a decision, read the standings.

The scored Track 1 feed is an MCP server. Its contract, taken from the brief and from the live
server's own tool schemas:

    hack26-get-tick          team, scenario ("outbreak-level-5" | "control-tick"), token optional
    hack26-submit-containment team, tick_id, action ("contain" | "evacuate" | "observe")
    hack26-get-scoreboard    no arguments

The cursor advances per team, and one answer per tick is accepted — a repeat returns the original
judgment. The fixture files published beside the brief are the same documents the feed serves, so
every decision can be rehearsed offline before a live tick is spent.

    python feed_mcp.py --fixtures        # offline: decide every published tick, submit nothing
    python feed_mcp.py --scoreboard      # read the standings
    python feed_mcp.py --live            # pull, decide, submit, read the judgment
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request

FEED_URL = os.environ.get("SCENARIO_MCP", "https://api.you.com/mcp/halloween-hack-26")
TEAM = os.environ.get("TEAM_HANDLE", "team-crimson-raven")
FIXTURE_BASE = ("https://raw.githubusercontent.com/youdotcom-oss/"
                "halloween-hack-2026/main/fixtures/")

# The action vocabulary of the scored feed.
ACTIONS = ("contain", "evacuate", "observe")


def rpc(method: str, params: dict, timeout: int = 45) -> dict:
    """One JSON-RPC call to the MCP server, reading the SSE frame it answers with."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(FEED_URL, data=body, headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    })
    with urllib.request.urlopen(req, timeout=timeout) as res:
        raw = res.read().decode()
    if "data: " in raw:
        raw = raw.split("data: ", 1)[1].split("\n\n", 1)[0]
    return json.loads(raw)


def call_tool(name: str, arguments: dict) -> dict:
    result = rpc("tools/call", {"name": name, "arguments": arguments})
    text = result["result"]["content"][0]["text"]
    return json.loads(text)


def get_tick(scenario: str, team: str = TEAM) -> dict:
    return call_tool("hack26-get-tick", {"team": team, "scenario": scenario})


def submit(tick_id: int, action: str, team: str = TEAM) -> dict:
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {ACTIONS}, got {action!r}")
    return call_tool("hack26-submit-containment",
                     {"team": team, "tick_id": tick_id, "action": action})


def scoreboard() -> dict:
    return call_tool("hack26-get-scoreboard", {})


def fixtures(scenario: str) -> dict:
    with urllib.request.urlopen(FIXTURE_BASE + scenario + ".json", timeout=45) as res:
        return json.load(res)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixtures", action="store_true", help="decide the published ticks, submit nothing")
    ap.add_argument("--scoreboard", action="store_true")
    ap.add_argument("--live", action="store_true", help="pull, decide and submit every tick")
    args = ap.parse_args()

    from policy import decide_tick

    if args.scoreboard:
        print(json.dumps(scoreboard(), indent=2, ensure_ascii=False))
    elif args.fixtures:
        for scenario in ("control-tick", "outbreak-level-5"):
            for tick in fixtures(scenario)["ticks"]:
                action, why = decide_tick(tick)
                print(f"{scenario:<18} tick {tick['tick_id']:<4} -> {action:<9} {why}")
    elif args.live:
        for scenario in ("outbreak-level-5", "control-tick"):
            while True:
                got = get_tick(scenario)
                tick = got["tick"]
                action, why = decide_tick(tick)
                print(f"tick {tick['tick_id']} -> {action}: {why}")
                print(json.dumps(submit(tick["tick_id"], action), indent=2, ensure_ascii=False))
                if got.get("exhausted"):
                    break
        print(json.dumps(scoreboard(), indent=2, ensure_ascii=False))
    else:
        ap.print_help()
