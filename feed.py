"""Where the swarm's facility data comes from.

`open_feed()` returns the local mock (facility_sim.Facility) unless FEED_URL is
set, in which case it talks HTTP to a running simulation. Both expose the same
four calls: observe(), advance(), contain(zone, action) and score().

When the starter repo's facility simulation is published, point FEED_URL at it
and, if its routes or field names differ, adapt `HttpFeed` below. Nothing else
in the template reads the feed directly.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from facility_sim import Facility


class FeedError(RuntimeError):
    pass


class LocalFeed:
    """The mock facility, in this process."""

    source = "local mock (facility_sim.py)"

    def __init__(self, seed: int, ticks: int):
        self.sim = Facility(seed=seed, ticks=ticks)

    def observe(self) -> dict:
        return self.sim.observe()

    def advance(self) -> dict:
        return self.sim.advance()

    def contain(self, zone: str, action: str) -> dict:
        return self.sim.contain(zone, action)

    def score(self) -> dict:
        return self.sim.score()

    @property
    def done(self) -> bool:
        return self.sim.done


class HttpFeed:
    """A simulation behind HTTP. Routes match `python facility_sim.py --serve PORT`."""

    def __init__(self, url: str, timeout: int = 15):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.source = self.url
        self._last: dict = {}

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else (b"{}" if method == "POST" else None)
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                return json.loads(res.read().decode() or "{}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise FeedError(f"{method} {self.url}{path} failed: {exc}") from exc

    def observe(self) -> dict:
        self._last = self._call("GET", "/observe")
        return self._last

    def advance(self) -> dict:
        self._last = self._call("POST", "/advance")
        return self._last

    def contain(self, zone: str, action: str) -> dict:
        return self._call("POST", "/contain", {"zone": zone, "action": action})

    def score(self) -> dict:
        return self._call("GET", "/score")

    @property
    def done(self) -> bool:
        last = self._last or self.observe()
        return last.get("tick", 0) >= last.get("ticks_total", 1)


def open_feed(seed: int = 31, ticks: int = 6):
    url = (os.environ.get("FEED_URL") or "").strip()
    return HttpFeed(url) if url else LocalFeed(seed, ticks)
