# shorts-caption-studio

**Animated word-by-word captions for vertical video — burned in locally, free, from your SRT.**

The animated captions that make Shorts hold attention — each word
lighting up as it's spoken — are the feature creators pay caption
subscriptions for: tools in that category run roughly **$20–40/month**
(about **₹1,900–3,800/month**) for what is, at its core, styling an
SRT file and burning it into the video. `shorts-caption-studio` does
that core job on your own machine: give it a transcript (Whisper SRT
is fine) and a vertical video, and it renders the highlight captions
in — or hands you just the styled `.ass` sidecar for your own editor.

- Pure Python 3 standard library — no dependencies, no install step
- Local only — your unreleased video never leaves your machine
- Three styles: `pop`, `karaoke`, `clean` (below)
- Script-friendly exit codes: `0` = clean, `1` = done with warnings,
  `2` = error

> **Honest note on word timing.** Whisper SRTs carry timing per
> *cue*, not per word. The word timings inside a cue are therefore
> **estimated**: each cue's duration is split proportionally to word
> length (longer word = longer on screen). It looks like real word
> timing and works well for short, punchy cues — but it is *not*
> true word-level alignment, and this tool never claims it is. For
> frame-accurate timing, run a word-level aligner upstream first.

## Styles

All styles are composed for vertical video (PlayRes 1080x1920) with
margins that keep captions out of the Shorts UI zones — the bottom
380px where captions/CTAs sit, and the top 220px title area.

| Style | Look | How it renders |
|---|---|---|
| `pop` | Big bold white words; the spoken word pops to accent yellow at 120% scale | one event per word, active word wrapped in colour + scale tags |
| `karaoke` | Each word fills from light grey to accent yellow as it's spoken | one event per cue, per-word `\kf` sweep tags (centisecond durations) |
| `clean` | Minimal plain white, no highlight, no animation | one event per cue, MarginV 460 — bottom-third safe area |

## Usage

You need Python 3.10+. Burn-in also needs
[ffmpeg](https://ffmpeg.org) (with ffprobe) on your PATH —
`--ass-only` mode is pure Python and works without it.

```bash
# 1. Burn captions into a video (writes demo.captioned.mp4 beside it)
python3 examples/make_examples.py   # once: generates examples/demo.mp4
python3 src/shorts_caption_studio.py examples/demo.mp4 --captions examples/demo.srt

# 2. Pick a style, choose the output name
python3 src/shorts_caption_studio.py examples/demo.mp4 --captions examples/demo.srt --style karaoke --out final.mp4

# 3. Or emit just the styled .ass sidecar (no ffmpeg needed)
python3 src/shorts_caption_studio.py --ass-only examples/demo.srt -o demo.pop.ass --style pop
```

How burn-in works: the tool probes the video with ffprobe, generates
a styled `.ass` file for the chosen style, and renders through
ffmpeg's `subtitles` filter pointed at that file. (An explicit styled
`.ass` is deliberate — the filter silently ignores `force_style`, so
generators that rely on it ship unstyled captions without noticing.)

Cues that cannot be used — empty text, or end ≤ start — are
**skipped with a named warning** and exit code 1; they are never
silently dropped and never rendered wrong. If *no* cue is usable,
that's an error (exit 2) and nothing is written. The input video is
never overwritten: `--out` pointing at it is refused.

## Use with AI agents

Both modes take `--json`: one JSON object with the same counts,
warnings and exit codes as the text report (errors come back as
`{"error": ...}`):

```bash
python3 src/shorts_caption_studio.py examples/demo.mp4 --captions examples/demo.srt --style karaoke --json
python3 src/shorts_caption_studio.py --ass-only examples/demo.srt -o demo.ass --json
```

Agents: read [SKILL.md](SKILL.md) first — commands, the full JSON
schemas, exit codes, and the honesty rules (estimated timing is not
alignment; a skipped cue is a caption missing from the render).

## Real run (verbatim)

```text
$ python3 src/shorts_caption_studio.py --ass-only examples/demo.srt -o demo.pop.ass --style pop
shorts-caption-studio v0.1.0 — ass-only
Captions: demo.srt — 3 cues, 12 words
Style: pop (big bold, active word in accent colour at 120% scale) · PlayRes 1080x1920
Word timing: ESTIMATED (cue duration split by word length — not true word alignment)
ASS written: demo.pop.ass (12 events)
(exit code: 0)
```

The sidecar it wrote (first lines; note the active word carrying the
accent colour and the 120% scale tags, moving word by word):

```text
[Script Info]
Title: shorts-caption-studio — pop captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Style: Pop,Arial,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,420,1

Dialogue: 0,0:00:00.00,0:00:00.38,Pop,,0,0,0,,{\1c&H0000D5FF\fscx120\fscy120}This{\r} trick changes everything
Dialogue: 0,0:00:00.38,0:00:00.87,Pop,,0,0,0,,This {\1c&H0000D5FF\fscx120\fscy120}trick{\r} changes everything
```

The same cue in `karaoke` style — one event, `\kf` centisecond
durations estimated per word (38 + 48 + 67 + 96 ≈ the 2.5s cue):

```text
Dialogue: 0,0:00:00.00,0:00:02.50,Karaoke,,0,0,0,,{\kf38}This {\kf48}trick {\kf67}changes {\kf96}everything
```

```text
$ python3 src/shorts_caption_studio.py examples/demo.mp4 --captions examples/demo.srt --style pop
shorts-caption-studio v0.1.0 — render
Video: demo.mp4 (720x1280, 6.0s)
Captions: demo.srt — 3 cues, 12 words
Style: pop (big bold, active word in accent colour at 120% scale) · PlayRes 1080x1920
Word timing: ESTIMATED (cue duration split by word length — not true word alignment)
Rendered: examples/demo.captioned.mp4 (12 caption events burned in)
(exit code: 0)
```

```text
$ python3 src/shorts_caption_studio.py examples/demo.mp4 --captions examples/demo.srt --style karaoke --json
{
  "tool": "shorts-caption-studio",
  "version": "0.1.0",
  "command": "render",
  "video": "demo.mp4",
  "path": "examples/demo.mp4",
  "captions": "demo.srt",
  "style": "karaoke",
  "output_file": "examples/demo.captioned.mp4",
  "width": 720,
  "height": 1280,
  "duration_seconds": 6.0,
  "has_audio": true,
  "cue_count": 3,
  "word_count": 12,
  "event_count": 3,
  "word_timing": "estimated",
  "skipped_cues": [],
  "warnings": []
}
(exit code: 0)
```

```text
$ python3 src/shorts_caption_studio.py missing.mp4 --captions examples/demo.srt
ERROR: file not found: missing.mp4
(exit code: 2)
```

## Tests

```bash
python3 -m unittest discover -s tests -v
# Ran 43 tests — OK
```

The suite covers both directions: the word-split math (equal words
split evenly, unequal words split proportionally, a single word
takes the whole cue), ASS time formatting, escaping of `{`, `}` and
`\` (with a test proving commas survive verbatim in the text field),
every style's UI-safe margins, pop's per-word highlight placement,
karaoke's `\kf` durations summing to the cue, clean's plain single
events, the parser's skipped-cue reporting, every CLI error path
(clean `ERROR:`, exit 2, no traceback), the no-ffmpeg split
(burn-in fails cleanly while `--ass-only` still works), JSON/text
agreement — and a real ffmpeg integration test that generates a
3-second vertical video, burns captions in, and probes the output's
size and duration. During development the demo render was also
frame-checked: the source frame's caption zone is one solid colour,
the burned frame has thousands of bright caption pixels in it.

## Internal use

This tool does a real job inside its author's own production engine:
it is the caption-styling step for the faceless Shorts channels
(**Leaked News** and **SADA — The Rooftop Catcher**), turning each
video's Whisper SRT into the burned-in animated captions the videos
are published with. It is not a demo in search of a purpose.

## Known limits

- **Word timing is estimated** (see the note at the top). Accuracy
  degrades inside long cues; keep cues short — caption-toolkit's
  `lint` (too-long > 7s) is a good upstream gate.
- Burn-in **re-encodes** the video (audio stream is copied
  untouched); expect ordinary re-encode quality behaviour.
- Styles are composed for vertical 1080x1920. Landscape input
  renders with a warning, but caption placement is not optimised
  for it.
- The font is Arial (libass falls back to a system sans where Arial
  is absent); there is no per-word font or colour customisation yet.
- Inline SRT tags (`<i>`, `<b>`) are stripped rather than converted
  to ASS styling.

## Privacy

What it touches: only the video and caption files you point it at
(and the one output file it writes). What it stores: nothing. What
it sends: nothing — there is no network code in this tool.

## Support

If this saves you a subscription month, consider sponsoring:
**https://github.com/sponsors/jasveerai88**

## Licence

MIT — see [LICENSE](LICENSE).
