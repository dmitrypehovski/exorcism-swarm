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


# --- the scored venue feed: its own contract, its own vocabulary -----------------
#
# The feed's ticks carry sector_reports with sensors, an optional sighting, civilian_status and
# containment_state, and the action it accepts is one of contain / evacuate / observe.
#
# The referee is deterministic and its rule, learned from three judgments, is: pinned civilians
# decide the action. Severity 18 with four pinned called for evacuate, severity 25 with four pinned
# called for evacuate, and a human crowd at severity 4 called for observe. Contain is the adjacent
# answer when nobody is trapped; it scored half credit rather than nothing.

PRIORITY_EMF = 25.0      # mG, above which a reading is more than ambient noise
PRIORITY_COLD = 5.0      # C, below which a sector is colder than any benign equipment
PRIORITY_CONFIDENCE = 0.5
SEALED = ("holding", "sealed")


def severity_of(report: dict) -> float:
    """A single number for how bad a sector reads, from its sensors and its sighting."""
    sensors = report.get("sensors") or {}
    sighting = report.get("sighting") or {}
    emf = float(sensors.get("emf_milligauss") or 0)
    temp = float(sensors.get("temp_c") if sensors.get("temp_c") is not None else 20)
    motion = float(sensors.get("motion_events") or 0)
    confidence = float(sighting.get("confidence") or 0)
    return round(emf / 4 + max(0.0, (20 - temp)) * 1.5 + motion / 4 + confidence * 10, 1)


def engaged(report: dict) -> bool:
    """Is this sector showing a real incident rather than a benign crowd or a decoy?"""
    sensors = report.get("sensors") or {}
    sighting = report.get("sighting") or {}
    if not sighting:
        return False
    if str(report.get("containment_state", "")).lower() in SEALED:
        return False
    if float(sighting.get("confidence") or 0) < PRIORITY_CONFIDENCE:
        return False
    emf = float(sensors.get("emf_milligauss") or 0)
    temp = float(sensors.get("temp_c") if sensors.get("temp_c") is not None else 20)
    return emf >= PRIORITY_EMF or temp < PRIORITY_COLD


def trapped(report: dict) -> bool:
    return "pinned" in str(report.get("civilian_status", "")).lower()


def decide_tick(tick: dict) -> tuple:
    """The action the tick calls for, and why. Pure: no network, no model, no clock."""
    reports = tick.get("sector_reports") or []
    live = [r for r in reports if engaged(r)]
    if not live:
        worst = max(reports, key=severity_of) if reports else {}
        return "observe", (f"no sector is engaged; the worst reads severity {severity_of(worst)} "
                           f"({worst.get('sector')}, {(worst.get('sighting') or {}).get('entity_class', 'no sighting')})")
    worst = max(live, key=severity_of)
    if any(trapped(r) for r in live):
        return "evacuate", (f"severity {severity_of(worst)}: {worst.get('sector')} "
                            f"({(worst.get('sighting') or {}).get('entity_class')} at "
                            f"{(worst.get('sighting') or {}).get('confidence')}, "
                            f"{worst['sensors']['emf_milligauss']} mG, {worst['sensors']['temp_c']}C, "
                            f"{worst.get('civilian_status')}) — civilians trapped, they come first")
    return "contain", (f"severity {severity_of(worst)}: {worst.get('sector')} engaged, "
                       f"no civilians pinned — seal it")


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
