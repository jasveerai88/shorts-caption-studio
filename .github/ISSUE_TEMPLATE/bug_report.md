---
name: Bug report
about: A render or sidecar that disagrees with the SRT, or a crash
title: "[bug] "
labels: bug
---

**What did you run?**
The exact command, e.g. `shorts-caption-studio video.mp4 --captions video.srt --style karaoke`.

**What did you expect?**
If the output looks wrong, say which cue and what it should have
done — "cue 3's third word highlights at 0:00:04.10 but the cue ends
at 0:00:04.00" — so the disagreement can be pinned to the parser,
the word split, or the render.

**What happened instead?**
Paste the full output, including the exit code if you saw one.

**Caption file**
Attach the SRT — trimmed to the cue(s) that reproduce it if it's
from a real project. Never attach an unreleased video to a public
issue; a generated test clip (see `examples/make_examples.py`) or
the `.ass` sidecar is almost always enough.

**Environment**
- shorts-caption-studio version (first line of any run):
- Python version:
- ffmpeg version (burn-in only):
- OS:
