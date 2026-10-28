"""Render the animated demo stage to MP4.

Playwright steps the page's own timeline (window.render(t)) and pipes JPEG frames straight into
ffmpeg, so the video is frame-accurate and reproducible from stage.html alone.

    python render_stage.py                 # full video
    python render_stage.py --preview 3     # three frames, for checking the layout
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FPS = 12
W, H = 1280, 720


def frames(page, fps: int, total: float, sink):
    n = int(total * fps)
    for i in range(n):
        t = i / fps
        page.evaluate(f"window.render({t:.4f})")
        sink.write(page.screenshot(type="jpeg", quality=92))
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=int, default=0, help="render N still frames and stop")
    ap.add_argument("--fps", type=int, default=FPS)
    args = ap.parse_args()

    with sync_playwright() as pw:
        # Playwright's bundled shell is not always downloaded; the system Chromium is present and
        # renders the same page, so prefer it when the bundle is missing.
        exe = None
        for candidate in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/local/bin/google-chrome"):
            if Path(candidate).exists():
                exe = candidate
                break
        browser = pw.chromium.launch(executable_path=exe,
                                     args=["--hide-scrollbars", "--force-device-scale-factor=1",
                                           "--no-sandbox"])
        page = browser.new_page(viewport={"width": W, "height": H})
        errors: list = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto((HERE / "stage.html").as_uri())
        page.wait_for_timeout(400)
        total = page.evaluate("window.TOTAL")
        if errors:
            print("page errors:", errors[:3], file=sys.stderr)

        if args.preview:
            for i, t in enumerate([2.0, 20.0, 38.0, 60.0, 84.0, 108.0, 130.0, 148.0][: args.preview * 3]):
                page.evaluate(f"window.render({t})")
                out = HERE / f"preview-{t:.0f}.png"
                page.screenshot(path=str(out))
                print("wrote", out.name)
            browser.close()
            return 0

        out = HERE / "exorcism-swarm-demo.mp4"
        proc = subprocess.Popen(
            ["ffmpeg", "-y", "-f", "mjpeg", "-r", str(args.fps), "-i", "-",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
             "-movflags", "+faststart", str(out)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        n = frames(page, args.fps, total, proc.stdin)
        proc.stdin.close()
        proc.wait()
        browser.close()
        print(f"{out}  {total:.0f}s  {n} frames  {out.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
