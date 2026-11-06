# Security policy

## Supported versions

The current 1.x release line is supported. Older versions are not
patched — install the current release.

## What this tool touches

shorts-caption-studio reads one local video file and one local SRT
file, and writes the one output you asked for (a rendered `.mp4` or
a styled `.ass`). It opens no network connections, collects no
telemetry, and sends nothing anywhere. Your unreleased video never
leaves your machine — that is the point of the tool.

Burn-in runs the system `ffmpeg`/`ffprobe` as subprocesses on the
files you point it at; the generated `.ass` path is escaped for the
`subtitles` filter. `--ass-only` mode runs no subprocess at all.

If you attach files to a public bug report, attach the SRT and a
minimal repro — never an unreleased video. Caption text can carry
unreleased titles, hooks and sponsorships; trim it to the cue that
reproduces the problem.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting on this repository:
**Security tab → Report a vulnerability**. Please do not open a
public issue for a suspected vulnerability.

## Correctness issues

A render whose captions disagree with the SRT's cues (a word
highlighted outside its cue's span, a skipped cue with no warning,
estimated timing presented as aligned anywhere in the output) is
treated as a correctness bug: open an issue with the SRT (trimmed
to the reproducing cue), the command you ran, and the output you
got. The honesty rules are the spec: skipped cues are reported,
never silently dropped, and estimated timing is labelled estimated.
