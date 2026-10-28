"""Narration for the 68-second record. Six short lines, no filler."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_voiceover as g  # reuse the retrying Gemini client

VO = Path(__file__).resolve().parent / "vo2"
LINES = [
    (1.0,  "Three ticks, three decisions, and every number here came from the venue feed."),
    (11.8, "Tick one forty-three: catering is breached, four civilians pinned. We evacuate."),
    (26.0, "Tick nine hundred is the trap. Forty-one motion events, and it is a crowd. We hold."),
    (38.0, "The feed scored us two point five of three, with zero false alarms."),
    (50.5, "The order went out to the room, and we read it back."),
    (59.0, "CrewAI, You.com, Parasail, One. Deterministic where it counts."),
]

if __name__ == "__main__":
    key = g.api_key()
    VO.mkdir(parents=True, exist_ok=True)
    timing = []
    for i, (start, text) in enumerate(LINES, 1):
        wav = VO / f"{i:02d}.wav"
        if not wav.exists():
            pcm = g.synthesize(text, key)
            import wave
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
            import subprocess, time
            subprocess.run(["ffmpeg","-y","-i",str(wav),"-filter:a","atempo=1.08","-c:a","libmp3lame","-b:a","128k",
                            str(VO / f"{i:02d}.mp3")], capture_output=True)
            print(f"  {i:02d} generated {len(pcm)/2/24000:.1f}s", flush=True)
            time.sleep(15)
        timing.append({"i": i, "start": start,
                       "dur": round(float(__import__("subprocess").run(
                           ["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",
                            str(VO / f"{i:02d}.mp3")], capture_output=True, text=True).stdout.strip() or 0), 2)})
    (VO / "timing.json").write_text(json.dumps(timing, indent=2))
    print("total", round(sum(t["dur"] for t in timing), 1), "s")
