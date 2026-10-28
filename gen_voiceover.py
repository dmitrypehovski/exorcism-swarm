"""Narrate the demo with Gemini TTS, one clip per scene.

The free tier rate-limits hard, so each line is retried with a growing backoff and finished clips are
skipped on a re-run. Timing is written to vo/timing.json and used by mux_demo.py.

    python gen_voiceover.py
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
VO = HERE / "vo"
MODEL = "gemini-2.5-flash-preview-tts"
VOICE = "Kore"

LINES = [
    (1.5, "Six sectors. Three agents. One question: is it a haunting, or is it just a crowd?"),
    (12.5, "Tick one forty-two. Catering reports ninety-eight milligauss, minus four degrees, four civilians pinned, sector breached."),
    (31.5, "Tick nine hundred is the trap. Forty-one motion events, the highest reading in the whole data set. And it is a crowd."),
    (53.5, "The swarm runs on CrewAI. A Sentinel that senses, an Analyst that grounds every claim against You-dot-com, a Dispatcher that acts."),
    (75.5, "The gate reads the channels. EMF and temperature together mean real. One channel alone means hold. Here four people are trapped, so the order is evacuate."),
    (100.5, "The venue feed judges every submission. Evacuate, evacuate, observe. Two and a half points, zero false alarms."),
    (123.5, "The order leaves the room through One, into the venue channel. And it is verified by reading the message back."),
    (142.5, "Deterministic where it counts, agentic everywhere else."),
]


def api_key() -> str:
    env = Path.home() / ".hermes" / "profiles" / "work2" / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("GEMINI_API_KEY", "")


def synthesize(text: str, key: str, attempts: int = 5) -> bytes:
    body = json.dumps({
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}}},
    }).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}"
    delay = 20
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as res:
                data = json.loads(res.read().decode())
            return base64.b64decode(data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 503) and attempt < attempts:
                print(f"    HTTP {exc.code}, waiting {delay}s (attempt {attempt}/{attempts})", flush=True)
                time.sleep(delay)
                delay = int(delay * 1.7)
                continue
            raise
    raise RuntimeError("unreachable")


def main() -> None:
    key = api_key()
    VO.mkdir(parents=True, exist_ok=True)
    timing = []
    for i, (start, text) in enumerate(LINES, 1):
        wav = VO / f"{i:02d}.wav"
        if wav.exists():
            with wave.open(str(wav)) as w:
                dur = w.getnframes() / w.getframerate()
            print(f"  {i:02d} cached {dur:.1f}s", flush=True)
        else:
            pcm = synthesize(text, key)
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(24000)
                w.writeframes(pcm)
            dur = len(pcm) / 2 / 24000
            subprocess.run(["ffmpeg", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "128k",
                            str(VO / f"{i:02d}.mp3")], capture_output=True)
            print(f"  {i:02d} generated {dur:.1f}s  ({start:.1f}s -> {start + dur:.1f}s)", flush=True)
            time.sleep(15)
        timing.append({"i": i, "start": start, "dur": round(dur, 2)})
    (VO / "timing.json").write_text(json.dumps(timing, indent=2))
    print("total speech", round(sum(t["dur"] for t in timing), 1), "s")


if __name__ == "__main__":
    main()
