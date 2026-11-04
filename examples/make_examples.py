#!/usr/bin/env python3
"""Generate the demo video used by the README (examples/demo.mp4).

A plain 720x1280 vertical colour clip with a soft tone, 6 seconds —
just enough to burn the demo captions into. Requires ffmpeg on PATH.
The generated .mp4 is gitignored; rebuild it any time with:

    python3 examples/make_examples.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    if shutil.which("ffmpeg") is None:
        print("ERROR: ffmpeg not found on PATH — cannot generate "
              "the demo video")
        return 2
    out = HERE / "demo.mp4"
    cmd = ["ffmpeg", "-y",
           "-f", "lavfi", "-i",
           "color=c=0x224488:s=720x1280:r=30:d=6",
           "-f", "lavfi", "-i", "sine=frequency=440:d=6",
           "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-shortest", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("ERROR: ffmpeg failed to generate demo.mp4")
        print(r.stderr[-500:])
        return 2
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
