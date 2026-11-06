---
name: shorts-caption-studio
description: Burn animated word-by-word highlight captions (pop / karaoke / clean styles) into vertical video from an SRT transcript, or emit just the styled .ass sidecar. Use when a finished vertical video (Shorts / TikTok / Reels) needs burned-in animated captions locally, or when an .ass with per-word highlight events is needed for another renderer. Word timing inside each cue is ESTIMATED from cue-level SRT — never present it as true word-level alignment. Install: pipx install git+https://github.com/jasveerai88/shorts-caption-studio
---

# shorts-caption-studio — agent skill

## Install

```bash
pipx install git+https://github.com/jasveerai88/shorts-caption-studio
# or: pip install git+https://github.com/jasveerai88/shorts-caption-studio
```

(Not on PyPI — the git+ form is the install.) This puts the
`shorts-caption-studio` command on your PATH. From a checkout, the
equivalent is `python3 src/shorts_caption_studio.py …` (Python 3.10+,
standard library only, zero dependencies). Burn-in additionally
needs the system ffmpeg + ffprobe on PATH; `--ass-only` does not.

## Purpose

Renders the animated-caption look (words highlight one by one as they
are spoken) from an SRT transcript: either burned into the video with
ffmpeg, or as a styled `.ass` sidecar for your own pipeline. Styles
are tuned for vertical video — PlayRes 1080x1920, margins that keep
text out of the Shorts UI zones (bottom 380px, top 220px). Pure
Python standard library; local only; burn-in shells out to the
system ffmpeg/ffprobe.

**The honesty core of this tool:** Whisper-style SRTs carry timing
per *cue*, not per word. Word start/end times inside a cue are
ESTIMATED by splitting the cue's duration proportionally to word
length (longer word = longer on screen). The output says
`"word_timing": "estimated"` and so must you.

## When to use / not use

Use when:
- A finished vertical video + its SRT transcript need burned-in
  animated captions, locally, with no upload and no subscription.
- You need a styled `.ass` (per-word events) to feed another
  renderer or editor (`--ass-only` — no ffmpeg required).

Do NOT use when:
- There is no transcript yet — this tool does not transcribe.
  Get an SRT first (Whisper etc.), then come back.
- You need frame-accurate word timing. Estimated splits drift from
  real speech inside long cues; use a word-level aligner upstream
  if that matters, and say so.
- The job is caption *quality* (reading speed, structure) — that is
  caption-toolkit's `check` / `lint`. This tool styles and renders;
  it does not judge the words.

## Commands

```bash
# Burn in (default style pop; writes <video>.captioned.mp4)
shorts-caption-studio VIDEO.mp4 --captions VIDEO.srt
shorts-caption-studio VIDEO.mp4 --captions VIDEO.srt \
    --style karaoke --out FINAL.mp4
shorts-caption-studio VIDEO.mp4 --captions VIDEO.srt --json

# Sidecar only (pure Python — works without ffmpeg)
shorts-caption-studio --ass-only VIDEO.srt -o VIDEO.ass
shorts-caption-studio --ass-only VIDEO.srt -o VIDEO.ass \
    --style clean --json
```

Arguments: positional `video` (burn-in mode); `--captions` (SRT,
required in burn-in mode); `--ass-only SRT` (sidecar mode, mutually
exclusive with a video); `-o` / `--out` (required in sidecar mode;
burn-in default `<video>.captioned.mp4`; never overwrites the input);
`--style` (`pop` default · `karaoke` · `clean`); `--json`.

Styles:
- `pop` — big bold white; the active word switches to accent yellow
  (`&H0000D5FF`) at 120% scale. One Dialogue event per word.
- `karaoke` — one event per cue with `\kf` centisecond sweep tags;
  each word fills light grey → accent yellow.
- `clean` — plain white, no highlight, no per-word events, MarginV
  460 (bottom-third safe area); the author's line breaks are kept
  as `\N`.

## Output JSON schema (`--json`)

Common fields: `tool` (`"shorts-caption-studio"`), `version`,
`command` (`"render"` / `"ass-only"`), `style`, `cue_count`,
`word_count`, `event_count`, `word_timing` (always `"estimated"`),
`skipped_cues` (list of `{index, reason, detail}` — reason is
`"empty-text"` or `"invalid-timing"`), `warnings` (list of strings),
`output_file`.

`render` adds: `video` (filename), `path` (as given), `captions`
(filename), `width`, `height`, `duration_seconds`, `has_audio` —
all measured by ffprobe, not taken from the filename.

`ass-only` adds: `captions` (filename). It reports no video facts
because it never probes one.

On error, stdout is a single object: `{"error": "<message>"}` with
exit code 2 — including argparse usage errors in `--json` mode.
Never plain text, never a traceback.

## Exit codes

- `0` — success, no warnings.
- `1` — success **with warnings**: some cues were skipped (they are
  NOT in the render — see `skipped_cues`), or the video is not
  vertical, or captions run past the end of the video. The output
  file exists and is real; report the warnings with it.
- `2` — ERROR: missing/unreadable input, no usable caption events,
  ffmpeg/ffprobe missing (burn-in only), non-video input, or a
  failed render. On a failed render any partial output is deleted —
  an existing `output_file` is never proof of a *failed* run, and a
  missing one after exit 2 is by design.

## Limits & honesty rules the agent must respect

- **Estimated is not aligned.** Never describe the word timing as
  accurate, synced, or measured — it is a length-proportional split
  of cue-level timing. The longer the cue, the rougher the estimate.
  If a human will judge sync quality, flag this before they watch.
- **A skipped cue is a missing caption.** Exit 1 with `skipped_cues`
  means those lines never appear on screen. Surface them; do not
  report the render as complete-with-all-captions.
- **A successful render proves the burn happened** — the tool checks
  the output exists and probes the input; it does not watch the
  result. Don't claim the captions "look right" without a frame
  check.
- **Burn-in re-encodes the video** (audio is copied untouched).
  Expect normal re-encode quality behaviour, and a render time
  roughly proportional to length.
- **Vertical-first.** Landscape input renders (with a warning) but
  the styles are composed for 1080x1920; positions will not be
  optimal.
- Inline HTML-ish tags in the SRT (`<i>` etc.) are stripped; `{`,
  `}` and `\` in caption text are escaped so they cannot corrupt
  the ASS styling; commas are preserved verbatim (legal in the ASS
  text field).
- Local only: the tool reads the files you point it at, writes the
  one output you asked for, and sends nothing anywhere.
