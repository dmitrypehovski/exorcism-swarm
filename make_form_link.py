"""Generate the pre-filled submission form link from the answers below.

    python make_form_link.py            # prints the URL
    python make_form_link.py --write    # also writes submission-form-url.txt
"""
from __future__ import annotations

import sys
from urllib.parse import urlencode

FORM = ("https://docs.google.com/forms/d/e/"
        "1FAIpQLSfsIkF2wgZEBcMwOTFuKyBZ5SKDl3UIdL6Ct1Zi05saFZxt8g/viewform")
TEAM_HANDLE = "team-crimson-raven"
REPO = "https://github.com/dmitrypehovski/exorcism-swarm"
# Pinned to the commit: jsDelivr caches @main, and an immutable URL always serves the cut we mean.
VIDEO = ("https://cdn.jsdelivr.net/gh/dmitrypehovski/exorcism-swarm@83bfe50e8d7ab71fb21798c32e2a3ba1e9f6ea46/"
         "demo/exorcism-swarm-demo.mp4")

DESCRIPTION = (
    "Exorcism Swarm is a supervised multi-agent system for The Exorcism Protocol. A CrewAI swarm of three "
    "roles - Sentinel, Analyst, Dispatcher - watches a facility feed, separates real spectral outbreaks from "
    "false alarms, and orders containment. Its distinguishing decision: false alarms are scored as failures, "
    "so the question whether an anomaly is real is not delegated to a language model. A deterministic gate "
    "reads the sensor channels first. A real outbreak drifts every channel together - EMF up, temperature "
    "down, motion up - and keeps drifting. A false alarm spikes exactly one channel for two or three ticks "
    "and fades, with a mundane cause named in the witness report. The venue feed judged our three submissions: "
    "evacuate on tick 142, evacuate on tick 143, observe on the control tick 900 - 2.5 of 3 points, zero false "
    "alarms. Tick 900 is the trap: 41 motion events, the highest reading in the data set, and it is a crowd, so "
    "acting on movement alone would have cost a false alarm. Tick 143 carries a decoy residual-echo at 0.35 "
    "confidence, not escalated. The swarm grounds and dispatches: You.com checks witness reports against live "
    "sources, Parasail serves the model, and One delivers each containment into the venue channel. A first live "
    "run of the swarm scored one false alarm on a single-channel anomaly; the gate was then given the last word "
    "and the same scenario now scores zero."
)

HOW = (
    "Every partner is load-bearing, and the pipeline is one line: CrewAI decides what to say, You.com grounds "
    "it, Parasail reasons, One delivers it. CrewAI runs the swarm - three agents with partial knowledge in a "
    "hierarchical process: the Sentinel reads the sectors and posts raw sightings, the Analyst holds or escalates "
    "each one, the Dispatcher issues the containment order. Remove CrewAI and there is no swarm. You.com grounds "
    "the Analyst: witness reports are checked against live web results so the swarm can tell lore from rumour, "
    "both directly through the Search API (POST https://ydc-index.io/v1/search, X-API-Key header, extraction "
    "'highlights') and through One's 'you' platform, which exposes the same grounding to the agents as a tool. "
    "Parasail is the brain - every agent's model, OpenAI-compatible with tool calling; our code probes Parasail "
    "before each run and keeps it as the default, and if it refuses inference (a key without a payment method "
    "returns 403) the run falls back to another provider and states which one served it, so a billing problem "
    "cannot stop the swarm mid-incident. One is the actuator: the three-tool loop - list integrations, find "
    "actions, execute action - through the One CLI and the MCP server, dispatching each containment with the "
    "channel passed as a path variable and the payload built from runtime state. One's own Discord platform "
    "refuses a venue server that a participant cannot install into, so dispatch.py tries One first and then the "
    "venue webhook the brief publishes for exactly this case, reporting which route carried the message. Either "
    "way the send is verified: Discord returns the created message and we report its id "
    "(1565115411777851473 in #loft-incident) rather than trusting a status code. Decisions are pure functions: "
    "python tests/test_decisions.py reproduces all three feed judgments offline."
)

ENTRIES = [
    ("entry.1195724611", "Dmitry Pehovski"),
    ("entry.1845628430", "dmitrypehovskiwork@gmail.com"),
    ("entry.1341422190", "ARLI Research, Founder"),
    ("entry.948566740", "https://www.linkedin.com/in/dmitry-pehovski/"),
    ("entry.646930071", "Exorcism Swarm"),
    ("entry.1644286487", f"Team name: {TEAM_HANDLE}. Members: Dmitry Pehovski, dmitrypehovskiwork@gmail.com"),
    ("entry.1905600922", "1"),
    ("entry.1526648627", 'Theme 1: "The Exorcism Protocol" (Autonomous Agent Swarms)'),
    ("entry.1415790015", 'Theme 1: "The Exorcism Protocol" (Autonomous Agent Swarms)'),
    ("entry.449407726", "Search API"),
    ("entry.449407726", "MCP"),
    ("entry.449407726", "Plugins / Skills"),
    ("entry.580176526", DESCRIPTION),
    ("entry.353881401", HOW),
    ("entry.1462185754", REPO),
    ("entry.316326554", VIDEO),
    ("entry.1767654033", "Project was built during the hackathon"),
    ("entry.1767654033", "GitHub repository is public with a README"),
    ("entry.1767654033", "Project used at least one You.com endpoint / MCP/ Plugin"),
]


def link() -> str:
    return FORM + "?usp=pp_url&" + urlencode(ENTRIES)


if __name__ == "__main__":
    url = link()
    print(url)
    if "--write" in sys.argv:
        with open("submission-form-url.txt", "w", encoding="utf-8") as fh:
            fh.write(url + "\n")
        print(f"\nwritten: submission-form-url.txt ({len(url)} chars)", file=sys.stderr)
