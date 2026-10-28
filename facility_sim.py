"""A small local stand-in for the starter repo's facility simulation.

The real simulation comes from the You.com starter repo. Until it is available
this mock gives the swarm something to watch: six zones, sensor readings every
tick, witness reports, civilians at risk, and a hidden ground truth. Some
anomalies are real outbreaks that cost civilians every tick they run; others
are false alarms with a mundane cause hidden in the evidence.

Scoring follows the judges: time to containment, false alarms, civilians saved.

    python facility_sim.py                    print a few ticks of the feed
    python facility_sim.py --serve 8077       serve it over HTTP, for FEED_URL=http://127.0.0.1:8077

HTTP routes (what feed.HttpFeed expects):
    GET  /observe            the current tick's observation
    POST /advance            move to the next tick, returns the new observation
    POST /contain            {"zone": "...", "action": "exorcise" | "evacuate"}
    GET  /score              the running score
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ZONES = ["Atrium", "Chapel", "Server Vault", "Cafeteria", "Morgue", "Greenhouse"]
ACTIONS = ("exorcise", "evacuate")

REAL_REPORTS = [
    "Saw a figure walk through the {zone} wall. Lights died, my breath is fogging.",
    "Something is whispering in the {zone}. Two people stopped answering the radio.",
    "Chairs in the {zone} are floating. Black ooze on the floor, it smells like sulfur.",
    "Security cam in the {zone} shows a shape with no face. Door handles are frozen.",
    "Colleague in the {zone} is speaking backwards and will not leave the room.",
]
FALSE_REPORTS = [
    ("Cold spot in the {zone}, it feels haunted. Facilities says the HVAC is being serviced today.", "temp"),
    ("Screaming in the {zone}! ... oh wait, it is the Halloween party playlist.", "audio"),
    ("Weird fog rolling through the {zone}. Someone left a fog machine on near the vents.", "motion"),
    ("Flickering lights and a buzzing in the {zone}. Could be the old breaker panel again.", "emf"),
    ("I swear a sheet just moved in the {zone}. Might be an intern in a ghost costume.", "motion"),
]


@dataclass
class Incident:
    zone: str
    start: int
    real: bool
    report: str
    spike: str = ""          # for a false alarm, the one sensor that spikes
    length: int = 3          # a false alarm fades after this many ticks
    contained_at: int | None = None
    evacuated_at: int | None = None
    lost: int = 0

    def active(self, tick: int) -> bool:
        if tick < self.start:
            return False
        if self.real:
            return self.contained_at is None
        return tick < self.start + self.length


@dataclass
class Facility:
    seed: int = 31
    ticks: int = 6
    outbreaks: int = 2
    false_alarms: int = 2
    tick: int = 0
    civilians: dict = field(default_factory=dict)
    incidents: list = field(default_factory=list)
    orders: list = field(default_factory=list)

    def __post_init__(self) -> None:
        rng = random.Random(self.seed)
        self.civilians = {z: rng.randint(8, 30) for z in ZONES}
        zones = rng.sample(ZONES, self.outbreaks + self.false_alarms)
        last_start = max(0, self.ticks - 3)
        for i, zone in enumerate(zones):
            start = rng.randint(0, last_start)
            if i < self.outbreaks:
                self.incidents.append(Incident(zone, start, True, rng.choice(REAL_REPORTS).format(zone=zone)))
            else:
                text, spike = rng.choice(FALSE_REPORTS)
                self.incidents.append(Incident(zone, start, False, text.format(zone=zone), spike=spike,
                                               length=rng.randint(2, 3)))
        self._rng = random.Random(self.seed * 7 + 1)

    # --- what the swarm can see ---------------------------------------------

    def observe(self) -> dict:
        """Everything the facility shows at this tick. Agents each get only a slice of it."""
        t = self.tick
        sensors = {}
        for zone in ZONES:
            rng = random.Random(f"{self.seed}:{t}:{zone}")
            reading = {"emf_mg": round(rng.uniform(0.8, 2.6), 1), "temp_c": round(rng.uniform(19.0, 21.5), 1),
                       "audio_db": rng.randint(34, 46), "motion_events": rng.randint(0, 2)}
            for inc in self.incidents:
                if inc.zone != zone or not inc.active(t):
                    continue
                k = t - inc.start
                if inc.real:
                    reading["emf_mg"] = round(reading["emf_mg"] + 6 + 2.5 * k, 1)
                    reading["temp_c"] = round(reading["temp_c"] - 4 - 2 * k, 1)
                    reading["audio_db"] += 18 + 4 * k
                    reading["motion_events"] += 5 + 2 * k
                elif inc.spike == "temp":
                    reading["temp_c"] = round(reading["temp_c"] - 6, 1)
                elif inc.spike == "audio":
                    reading["audio_db"] += 30
                elif inc.spike == "emf":
                    reading["emf_mg"] = round(reading["emf_mg"] + 7, 1)
                else:
                    reading["motion_events"] += 6
            sensors[zone] = reading
        reports = [{"zone": inc.zone, "text": inc.report, "tick": inc.start}
                   for inc in self.incidents if inc.start <= t and (inc.active(t) or inc.start == t)]
        return {"tick": t, "ticks_total": self.ticks, "sensors": sensors, "reports": reports,
                "roster": dict(self.civilians), "zones": list(ZONES)}

    def advance(self) -> dict:
        """Close out this tick (an unchecked outbreak costs civilians) and move to the next one."""
        for inc in self.incidents:
            if inc.real and inc.active(self.tick) and inc.evacuated_at is None:
                k = self.tick - inc.start
                loss = min(self.civilians[inc.zone], 2 + k)
                self.civilians[inc.zone] -= loss
                inc.lost += loss
        self.tick += 1
        return self.observe()

    @property
    def done(self) -> bool:
        return self.tick >= self.ticks

    # --- what the swarm can do ----------------------------------------------

    def contain(self, zone: str, action: str) -> dict:
        if zone not in ZONES:
            return {"ok": False, "error": f"unknown zone {zone!r}. Zones: {', '.join(ZONES)}"}
        if action not in ACTIONS:
            return {"ok": False, "error": f"unknown action {action!r}. Actions: {', '.join(ACTIONS)}"}
        live = [i for i in self.incidents if i.real and i.zone == zone and i.active(self.tick)]
        order = {"tick": self.tick, "zone": zone, "action": action}
        if not live:
            order.update(outcome="false_alarm", detail=f"field team found nothing paranormal in the {zone}")
            self.orders.append(order)
            return {"ok": True, **order}
        inc = live[0]
        saved = self.civilians[zone]
        if action == "exorcise":
            inc.contained_at = self.tick
            order.update(outcome="contained", ticks_to_contain=self.tick - inc.start + 1, start_tick=inc.start,
                         civilians_saved=saved, detail=f"outbreak in the {zone} contained, {saved} civilians safe")
        else:
            inc.evacuated_at = self.tick
            self.civilians[zone] = 0  # out of harm's way, and not counted twice by a later exorcism
            order.update(outcome="evacuated", civilians_saved=saved, start_tick=inc.start,
                         detail=f"{saved} civilians evacuated from the {zone}; the outbreak is still active")
        self.orders.append(order)
        return {"ok": True, **order}

    def score(self) -> dict:
        real = [i for i in self.incidents if i.real]
        contained = [i for i in real if i.contained_at is not None]
        ticks = [i.contained_at - i.start + 1 for i in contained]
        saved = sum(o.get("civilians_saved", 0) for o in self.orders if o["outcome"] in ("contained", "evacuated"))
        at_risk = sum(i.lost for i in real) + sum(self.civilians[i.zone] for i in real)
        return {
            "outbreaks": len(real),
            "contained": len(contained),
            "missed": len(real) - len(contained),
            "mean_ticks_to_contain": round(sum(ticks) / len(ticks), 2) if ticks else None,
            "false_alarms": sum(1 for o in self.orders if o["outcome"] == "false_alarm"),
            "civilians_saved": saved,
            "civilians_lost": sum(i.lost for i in real),
            "civilians_at_risk": at_risk,
            "orders": len(self.orders),
        }


def serve(port: int, facility: Facility) -> None:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict) -> None:
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):  # noqa: N802 - http.server naming
            if self.path == "/observe":
                return self._send(200, facility.observe())
            if self.path == "/score":
                return self._send(200, facility.score())
            return self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
            if self.path == "/advance":
                return self._send(200, facility.advance())
            if self.path == "/contain":
                return self._send(200, facility.contain(str(body.get("zone", "")), str(body.get("action", ""))))
            return self._send(404, {"error": "not found"})

        def log_message(self, *_):
            pass

    print(f"facility sim on http://127.0.0.1:{port}  (FEED_URL=http://127.0.0.1:{port})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=31)
    ap.add_argument("--ticks", type=int, default=6)
    ap.add_argument("--serve", type=int, metavar="PORT", help="serve the sim over HTTP on this port")
    args = ap.parse_args()
    facility = Facility(seed=args.seed, ticks=args.ticks)
    if args.serve:
        serve(args.serve, facility)
        return
    while not facility.done:
        obs = facility.observe()
        print(f"tick {obs['tick']}")
        for zone, s in obs["sensors"].items():
            print(f"  {zone:<13} emf {s['emf_mg']:>5} mG  temp {s['temp_c']:>5} C  audio {s['audio_db']:>3} dB  "
                  f"motion {s['motion_events']:>2}  civilians {obs['roster'][zone]}")
        for r in obs["reports"]:
            print(f"  report from the {r['zone']}: {r['text']}")
        facility.advance()
    print("score with no containment at all:", json.dumps(facility.score()))


if __name__ == "__main__":
    main()
