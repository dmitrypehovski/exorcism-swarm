"""Put the narration under the rendered video.

Each clip is delayed to its scene's start and mixed down. The video stream is copied, not re-encoded.

    python mux_demo.py            # -> exorcism-swarm-demo-narrated.mp4
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
VO = HERE / "vo"


def main() -> None:
    timing = json.loads((VO / "timing.json").read_text())
    video = HERE / "exorcism-swarm-demo.mp4"
    clips = [VO / f"{t['i']:02d}.mp3" for t in timing]
    missing = [str(c) for c in clips if not c.exists()]
    if missing:
        raise SystemExit(f"missing narration: {missing}")

    args = ["ffmpeg", "-y", "-i", str(video)]
    for clip in clips:
        args += ["-i", str(clip)]

    parts, labels = [], []
    for n, t in enumerate(timing, start=1):
        ms = int(round(t["start"] * 1000))
        parts.append(f"[{n}:a]adelay={ms}:all=1[a{n}]")
        labels.append(f"[a{n}]")
    parts.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0[aout]")
    filt = ";".join(parts)

    out = HERE / "exorcism-swarm-demo-narrated.mp4"
    args += ["-filter_complex", filt, "-map", "0:v", "-map", "[aout]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    subprocess.run(args, check=True)
    print(f"{out}  {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
