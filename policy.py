"""Deterministic escalation gate for the facility simulation.

Why this exists: false alarms are a scored failure, so the decision *whether* an anomaly is real
must not be delegated to a language model. The model explains and dispatches; this gate decides.

The simulation gives an exact discriminator:

* a real outbreak drifts **every** sensor together and keeps drifting (emf up, temp down,
  audio up, motion up, growing with each tick it runs unchecked);
* a false alarm spikes exactly **one** sensor for two or three ticks and fades, and its witness
  report usually names a mundane cause (HVAC, fog machine, party playlist, breaker panel).

So: two or more independent anomalies, and specifically EMF together with temperature, means real.
One anomaly means benign. The report text is used only to confirm, never to overrule the sensors.
"""
from __future__ import annotations

# Generous bounds: a benign reading never leaves this band, an outbreak leaves it on the first tick.
NORMAL = {"emf_mg": 4.0, "temp_c": 17.5, "audio_db": 52, "motion_events": 4}

MUNDANE_CAUSES = ("hvac", "fog machine", "party playlist", "breaker panel", "intern in a ghost",
                  "facilities says", "could be the old")

PARANORMAL_MARKERS = ("figure", "whisper", "floating", "ooze", "no face", "frozen", "backwards",
                      "stopped answering", "fogging")


def zone_signals(reading: dict) -> dict:
    """Which sensors are outside the benign band."""
    flags = {}
    if reading.get("emf_mg", 0) > NORMAL["emf_mg"]:
        flags["emf"] = reading["emf_mg"]
    if reading.get("temp_c", 20) < NORMAL["temp_c"]:
        flags["temp"] = reading["temp_c"]
    if reading.get("audio_db", 40) > NORMAL["audio_db"]:
        flags["audio"] = reading["audio_db"]
    if reading.get("motion_events", 0) > NORMAL["motion_events"]:
        flags["motion"] = reading["motion_events"]
    return flags


def zone_verdict(zone: str, reading: dict, report: str = "") -> dict:
    flags = zone_signals(reading)
    text = (report or "").lower()
    mundane = next((m for m in MUNDANE_CAUSES if m in text), None)
    paranormal = [m for m in PARANORMAL_MARKERS if m in text]

    joint = "emf" in flags and "temp" in flags
    multi = len(flags) >= 3
    real = joint or multi

    if real:
        reason = ("emf and temperature are both outside the benign band"
                  if joint else f"{len(flags)} sensors outside the benign band")
        if paranormal:
            reason += f"; the report describes {paranormal[0]}"
    elif flags:
        reason = f"only {next(iter(flags))} is outside the band, consistent with a mundane cause"
        if mundane:
            reason += f" ({mundane})"
    else:
        reason = "all sensors within the benign band"

    return {"zone": zone, "real": real, "flags": flags, "mundane": mundane,
            "paranormal_markers": paranormal, "reason": reason}


def tick_verdict(observation: dict) -> dict:
    """Rank the zones that need an order this tick, worst first."""
    reports = {}
    for r in observation.get("reports", []):
        reports.setdefault(r.get("zone"), r.get("text", ""))
    verdicts = [zone_verdict(z, reading, reports.get(z, ""))
                for z, reading in (observation.get("sensors") or {}).items()]
    hot = [v for v in verdicts if v["real"]]

    def severity(v: dict) -> float:
        return (v["flags"].get("emf", 0) - NORMAL["emf_mg"]) + (NORMAL["temp_c"] - v["flags"].get("temp", 99))

    hot.sort(key=severity, reverse=True)
    return {"zones": verdicts, "hot": [v["zone"] for v in hot],
            "action": "exorcise" if hot else None,
            "rationale": hot[0]["reason"] if hot else "no zone shows a joint anomaly"}
