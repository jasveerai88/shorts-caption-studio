# Contributing

Contributions are welcome — bug reports, fixes and small focused features.

## Ground rules

- **Standard library only.** shorts-caption-studio's promise is
  "clone and run" (plus ffmpeg for burn-in, which stays an external
  tool, never a Python dependency). Pull requests that add a
  third-party dependency will not be merged.
- **Local only.** No network calls, no telemetry, no uploads of user
  files.
- **Estimated stays labelled estimated.** Word timings are split from
  cue-level SRT input. Never present them — in code, docs, output or
  a PR description — as measured or aligned word timing.
- **Skipped cues are reported, never silently dropped.** Any change
  to the parser keeps the skip reasons visible in text and JSON.
- **Both directions tested.** A behaviour change needs a test where
  good input succeeds and bad input fails cleanly — not just one side.

## Getting started

```bash
git clone https://github.com/jasveerai88/shorts-caption-studio
cd shorts-caption-studio
python3 -m unittest discover -s tests -v
python3 examples/make_examples.py
python3 src/shorts_caption_studio.py examples/demo.mp4 --captions examples/demo.srt
```

## Pull requests

1. Fork, branch, and keep the change to one topic.
2. Add or update tests under `tests/`; the full suite must pass.
3. Note the change in `CHANGELOG.md` under an "Unreleased" heading.
4. Describe the behaviour change with a real before/after run if the
   CLI output changes.
