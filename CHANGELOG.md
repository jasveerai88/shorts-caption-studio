# Changelog

## v1.0.0 — 2026-11-04

The professional release. The engine is unchanged — same parser,
same estimated word split, same styles, same exit codes — rebuilt
to the standard of a tool you install once and keep.

- **Installable package.** `pyproject.toml` with the console entry
  point `shorts-caption-studio`. Install with pipx or pip from the
  GitHub repo (`pipx install
  git+https://github.com/jasveerai88/shorts-caption-studio`);
  running the source checkout directly still works. Verified: a
  clean-venv install followed by the README quickstart produces
  output byte-identical to the source runs, exit codes included.
- **README as a landing page.** The before/after leads (frames from
  a real render of the bundled example), the honest limits moved up
  front — no transcription, SRT-in only, no timing repair, and word
  timing ESTIMATED, labelled in every report — and a comparison
  table scoped to the caption step against the named subscription
  alternative (Submagic Starter $19/member/month for 15 videos,
  submagic.co/pricing read 2026-11-04).
- **Demo GIF** built from real runs (the bundled SRT styled, the
  actual render's frames before/after, the broken-cue run), and a
  social preview image.
- **New bundled fixture `examples/messy.srt`** — a 4-cue SRT with a
  reversed cue and an empty cue, so the skipped-cue warnings and
  exit code 1 are reproducible verbatim from the README.
- **`SECURITY.md`** and issue templates: bug reports use the
  minimal-repro standard (attach the SRT, not your unreleased
  video).
- **`SKILL.md`** updated to the installed command and the git+
  install.
- No behaviour changes; version strings only. 43 tests, all
  passing.

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
