"""Render the demo video: 1280x720 terminal-style frames piped straight into ffmpeg.

No screen recorder, no GUI: the frames are drawn with PIL and encoded by ffmpeg, so the video is
reproducible from this file alone.

    python make_demo.py            # writes demo/exorcism-swarm-demo.mp4
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1280, 720, 15
BG = (13, 17, 23)
BAR = (22, 27, 34)
FG = (201, 209, 217)
DIM = (110, 118, 129)
CYAN = (86, 212, 221)
GREEN = (63, 185, 80)
YELLOW = (210, 168, 62)
RED = (248, 81, 73)
PURPLE = (167, 139, 250)

MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SANS_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

F = {
    "cmd": ImageFont.truetype(MONO_B, 21),
    "out": ImageFont.truetype(MONO, 21),
    "small": ImageFont.truetype(MONO, 18),
    "title": ImageFont.truetype(SANS_B, 58),
    "sub": ImageFont.truetype(SANS_B, 26),
    "head": ImageFont.truetype(SANS_B, 30),
    "foot": ImageFont.truetype(MONO, 17),
}

# Each scene: (duration, kind, [lines]). A line is (text, colour, style).
# style: "cmd" (typed, prefixed), "out", "small", "head", "big", "sub"
SCENES = [
    (11, "title", [
        ("EXORCISM SWARM", CYAN, "big"),
        ("Track 1 — The Exorcism Protocol", FG, "sub"),
        ("You.com Halloween Hack 2026 · AWS Builder Loft, San Francisco", DIM, "small"),
        ("", FG, "small"),
        ("github.com/dmitrypehovski/exorcism-swarm", PURPLE, "small"),
    ]),
    (28, "term", [
        ("The decision is deterministic, not a vibe", CYAN, "head"),
        ("$ python validate.py --seeds 200", FG, "cmd"),
        ("", FG, "out"),
        ("seeds: 200  ticks: 6", DIM, "out"),
        ("outbreaks total: 400  contained: 400  (100.0%)", GREEN, "out"),
        ("false alarms total: 0", GREEN, "out"),
        ("civilians lost total: 0", GREEN, "out"),
        ("civilians saved total: 7678", FG, "out"),
        ("mean ticks to contain: 1.0", FG, "out"),
        ("seeds with zero misses and zero false alarms: 200/200", GREEN, "out"),
        ("", FG, "out"),
        ("400 outbreaks across 200 facilities. Not one false alarm.", YELLOW, "small"),
    ]),
    (26, "term", [
        ("Why it holds", CYAN, "head"),
        ("a real outbreak   every sensor drifts together, and keeps drifting", FG, "out"),
        ("a false alarm     exactly one sensor spikes, then fades", FG, "out"),
        ("", FG, "out"),
        ("gate rule   EMF and temperature both out of band   ->  real", GREEN, "out"),
        ("            exactly one sensor out of band        ->  benign, hold", RED, "out"),
        ("", FG, "out"),
        ("held:  motion-only, witness report 'intern in a ghost costume'", DIM, "small"),
        ("held:  audio-only,  witness report 'Halloween party playlist'", DIM, "small"),
        ("", FG, "out"),
        ("The model explains and argues. It does not get to spend a false alarm.", YELLOW, "small"),
    ]),
    (26, "term", [
        ("The live run, dispatch on", CYAN, "head"),
        ("$ SIM_TICKS=3 python main.py", FG, "cmd"),
        ("", FG, "out"),
        ("Outbreaks contained               2/2", GREEN, "out"),
        ("Mean ticks to containment         1.0", FG, "out"),
        ("Mean seconds to containment       74.1", FG, "out"),
        ("False alarms                      0", GREEN, "out"),
        ("Civilians saved                   31 of 31 at risk", FG, "out"),
        ("Civilians lost                    0", GREEN, "out"),
        ("", FG, "out"),
        ("First live run scored 1 false alarm (ARL-7).", RED, "small"),
        ("The gate was then given the last word. Same seed: zero.", GREEN, "small"),
    ]),
    (22, "term", [
        ("Verified outside this machine, read back through One", CYAN, "head"),
        ("", FG, "out"),
        ("Slack  #loft-incident    15 messages, every order linked to its issue", FG, "out"),
        ("Linear ARL-5, ARL-6      contained", GREEN, "out"),
        ("Linear ARL-7             the false alarm the gate now prevents", RED, "out"),
        ("Linear ARL-8, ARL-9      contained, gated run", GREEN, "out"),
        ("", FG, "out"),
        ("You.com   reached directly and through One's you platform", FG, "out"),
        ("", FG, "out"),
        ("The dispatch is not a print statement.", YELLOW, "small"),
    ]),
    (14, "title", [
        ("CrewAI runs the swarm.", FG, "sub"),
        ("You.com grounds it.", FG, "sub"),
        ("Parasail is the brain.", FG, "sub"),
        ("One delivers it to the room.", FG, "sub"),
        ("", FG, "small"),
        ("github.com/dmitrypehovski/exorcism-swarm", PURPLE, "small"),
    ]),
]


def frame(t: float) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # window chrome
    d.rectangle([0, 0, W, 34], fill=BAR)
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse([16 + i * 22, 11, 28 + i * 22, 23], fill=c)
    d.text((W - 300, 9), "exorcism-swarm — live demo", font=F["foot"], fill=DIM)

    # which scene are we in
    elapsed = 0.0
    for dur, kind, lines in SCENES:
        if t < elapsed + dur:
            local = t - elapsed
            break
        elapsed += dur
    else:
        return img

    if kind == "title":
        y = 190
        for i, (text, colour, style) in enumerate(lines):
            appear = 0.35 * i
            if local < appear:
                continue
            alpha = min(1.0, (local - appear) / 0.6)
            colour = tuple(int(BG[j] + (colour[j] - BG[j]) * alpha) for j in range(3))
            f = {"big": F["title"], "sub": F["sub"], "small": F["small"]}.get(style, F["out"])
            w = d.textlength(text, font=f)
            d.text(((W - w) / 2, y), text, font=f, fill=colour)
            y += {"big": 84, "sub": 46, "small": 34}.get(style, 30)
        return img

    # terminal scene: reveal lines in sequence, commands typed out
    y = 72
    reveal = 0.0
    for text, colour, style in lines:
        reveal += 0.22 if style != "cmd" else 1.15
        if local < reveal - (1.15 if style == "cmd" else 0.22):
            continue
        if style == "head":
            d.text((56, y), text, font=F["head"], fill=colour)
            y += 46
            d.line([56, y - 12, W - 56, y - 12], fill=(48, 54, 61), width=1)
            y += 6
            continue
        f = F["cmd"] if style == "cmd" else (F["small"] if style == "small" else F["out"])
        shown = text
        if style == "cmd":
            typed = max(0.0, min(1.0, (local - (reveal - 1.15)) / 1.0))
            shown = text[: max(1, int(len(text) * typed))]
        d.text((56, y), shown, font=f, fill=colour)
        if style == "cmd" and shown == text and (local * 3) % 2 < 1:
            w = d.textlength(shown, font=f)
            d.rectangle([56 + w + 3, y + 2, 56 + w + 12, y + 24], fill=FG)
        y += 30 if style in ("out", "cmd") else 26
    return img


def main() -> None:
    out = Path(__file__).resolve().parent / "demo" / "exorcism-swarm-demo.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    total = sum(s[0] for s in SCENES)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart",
         str(out)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for n in range(int(total * FPS)):
        proc.stdin.write(frame(n / FPS).tobytes())
    proc.stdin.close()
    proc.wait()
    print(f"{out}  {total:.0f}s  {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
