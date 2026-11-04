# Changelog

## v0.1.0 — 2026-11-04

First release.

- **Burn-in mode** — `VIDEO --captions SRT [--style ...] [--out ...]`:
  probes the video with ffprobe (frame size, duration, audio),
  generates a styled `.ass`, and burns it in with ffmpeg's `subtitles`
  filter (an explicit styled file — the filter silently ignores
  `force_style`). Default output is `<video>.captioned.mp4` beside
  the input; the input is never overwritten.
- **`--ass-only SRT -o OUT.ass`** — emits just the styled sidecar.
  Pure Python: no ffmpeg needed, works anywhere.
- **Three styles**, all PlayRes 1080x1920 with margins that keep text
  out of the Shorts UI zones (bottom 380px): `pop` (big bold, active
  word in accent yellow at 120% scale), `karaoke` (per-word `\kf`
  fill sweep, grey → accent), `clean` (plain, no highlight, MarginV
  460 bottom-third safe area).
- **Estimated word timing, labelled as such everywhere.** Whisper
  SRTs are cue-level, so word timings inside a cue are split
  proportionally to word length. The human report, the JSON
  (`"word_timing": "estimated"`) and this changelog all say
  *estimated* — the tool never claims true word-level alignment.
- **Honest failure, always.** Missing files, unparseable SRTs,
  non-video input, missing ffmpeg/ffprobe and failed renders are
  clean `ERROR:` exits (code 2) — no tracebacks, and a failed render
  deletes any partial output instead of leaving a fake success.
  Cues that cannot be used (empty text, end ≤ start) are skipped
  with named warnings and exit code 1, never silently dropped.
- **`--json` on both modes** — one JSON object with the same counts,
  warnings and exit codes as the text report; errors are
  `{"error": ...}` objects (usage errors included).
- **`SKILL.md`** at the repo root for AI coding agents: purpose, when
  to use / not use, exact commands, the JSON schemas, exit codes, and
  the honesty rules (estimated timing is not alignment; a cue skipped
  is a cue missing from the render).
- Bundled example: `examples/demo.srt` plus `examples/make_examples.py`
  (generates the 6-second vertical demo video the README renders).
- 43 stdlib-unittest tests: word-split math both directions, ASS
  escaping (`{`, `}`, `\`; commas proven legal in the text field),
  style/UI-margin invariants, per-style event generation, parser
  skipped-cue reporting, every CLI error path, the no-ffmpeg split
  (burn-in errors cleanly, `--ass-only` still works), JSON/text
  agreement, and a real ffmpeg integration test that generates a
  3-second vertical video, burns captions in, and probes the result.
- Pure Python standard library; local only; MIT licence.
