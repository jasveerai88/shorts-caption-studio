#!/usr/bin/env python3
"""shorts-caption-studio — burn animated word-highlight captions into
vertical video, locally and free. Or emit just the styled .ass sidecar.

Takes an SRT transcript (Whisper output is cue-level) plus a vertical
video and renders the animated-caption look the paid tools sell —
word-by-word highlight, burned in with ffmpeg's subtitles filter using
a *generated styled .ass file* (never force_style: ffmpeg's subtitles
filter silently ignores it; an explicit styled .ass is the reliable
route).

WORD TIMING IS ESTIMATED — say it plainly. Whisper SRTs carry timing
per cue, not per word, so the word start/end times inside a cue are
ESTIMATED by splitting the cue's duration proportionally to word
length (longer word = longer on screen). The result looks like real
word timing; it is not true word-level alignment and this tool never
claims it is. If you need frame-accurate word timing, transcribe with
a word-level aligner first.

Styles (PlayRes 1080x1920, vertical-first; margins keep captions out
of the Shorts UI zones — bottom 380px, top 220px):
  pop     — big bold white words; the active word switches to the
            accent colour and pops to 120% scale.
  karaoke — one event per cue with \\kf sweep tags: each word fills
            from light grey to the accent colour over its (estimated)
            duration.
  clean   — minimal: plain white words, no highlight, no animation,
            set higher (MarginV 460) in the bottom-third safe area.

Commands:
  shorts_caption_studio.py VIDEO --captions SRT [--style pop]
                           [--out OUT.mp4] [--json]
  shorts_caption_studio.py --ass-only SRT -o OUT.ass [--style pop]
                           [--json]

Exit codes: 0 = clean success, 1 = success with warnings (some cues
skipped, or the video is not vertical / captions overrun it),
2 = ERROR (missing or unusable input, ffmpeg missing or failed) —
errors print ``ERROR: ...`` (or {"error": ...} with --json), never a
traceback, and a failed render never leaves a fake output behind.

With --json, both modes print one JSON object instead of the text
report (same details, same exit codes). See SKILL.md for the schema.

Needs: Python 3.10+. Burn-in also needs ffmpeg + ffprobe on PATH;
--ass-only is pure Python and works without them.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

VERSION = "0.1.0"
TOOL = "shorts-caption-studio"

PLAY_RES_X = 1080
PLAY_RES_Y = 1920
SHORTS_BOTTOM_UI_PX = 380      # caption/CTA zone — keep text above it
ACCENT = "&H0000D5FF"          # #FFD500 yellow, ASS &HAABBGGRR
WHITE = "&H00FFFFFF"
KARAOKE_UNFILLED = "&H00D9D9D9"
OUTLINE_COLOUR = "&H00000000"
SHADOW_COLOUR = "&H64000000"
POP_SCALE = 120                # % — the active word's pop in `pop`
RENDER_TIMEOUT = 1200          # seconds for one ffmpeg render

# style name -> ASS style fields (all Alignment 2 = bottom-centre)
STYLES = {
    "pop": {
        "ass_name": "Pop", "fontsize": 84, "primary": WHITE,
        "secondary": WHITE, "outline": 6, "shadow": 2, "margin_v": 420,
        "blurb": "big bold, active word in accent colour at 120% scale",
    },
    "karaoke": {
        "ass_name": "Karaoke", "fontsize": 76, "primary": ACCENT,
        "secondary": KARAOKE_UNFILLED, "outline": 5, "shadow": 2,
        "margin_v": 420,
        "blurb": "active word fills grey -> accent (\\kf sweep)",
    },
    "clean": {
        "ass_name": "Clean", "fontsize": 64, "primary": WHITE,
        "secondary": WHITE, "outline": 3, "shadow": 1, "margin_v": 460,
        "blurb": "minimal, no highlight, bottom-third safe margin",
    },
}


class ToolError(Exception):
    """A clean, user-facing failure (printed as ERROR, exit 2)."""


# --------------------------------------------------------------------------
# SRT parsing — cue-level events in, skipped cues reported, never hidden
# --------------------------------------------------------------------------

_TIMING_RE = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*"
    r"(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3})")


def _ts_to_sec(ts):
    ts = ts.replace(",", ".")
    parts = [float(x) for x in ts.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


@dataclass
class Cue:
    index: int          # position among timed cues in the file, 1-based
    start: float
    end: float
    text: str           # caption text, lines joined with "\n"


def parse_srt_text(text):
    """Parse SRT text -> (cues, skipped).

    skipped is a list of {"index", "reason"} for timed cues that could
    not be used: "empty-text" (no words) or "invalid-timing"
    (end <= start). They are reported to the user, never dropped
    silently and never rendered.
    """
    cues, skipped = [], []
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    index = 0
    for block in re.split(r"\n\s*\n", text):
        lines = block.split("\n")
        timing_at, match = None, None
        for i, line in enumerate(lines):
            match = _TIMING_RE.search(line)
            if match:
                timing_at = i
                break
        if timing_at is None:
            continue                      # index numbers, headers, junk
        index += 1
        start = _ts_to_sec(match.group(1))
        end = _ts_to_sec(match.group(2))
        body = [ln.strip() for ln in lines[timing_at + 1:]]
        body = [re.sub(r"<[^>]+>", "", ln) for ln in body if ln]
        caption = "\n".join(body).strip()
        if end <= start:
            skipped.append({"index": index, "reason": "invalid-timing",
                            "detail": f"end {end:.3f}s <= start "
                                      f"{start:.3f}s"})
            continue
        if not caption:
            skipped.append({"index": index, "reason": "empty-text",
                            "detail": "cue has no text"})
            continue
        cues.append(Cue(index=index, start=start, end=end,
                        text=caption))
    return cues, skipped


# --------------------------------------------------------------------------
# estimated word timing — the cue duration split by word length
# --------------------------------------------------------------------------

@dataclass
class Word:
    text: str
    start: float
    end: float


def split_words(cue):
    """Split a cue into words with ESTIMATED timings.

    Each word's share of the cue duration is proportional to its
    character length. These are estimates from cue-level input — see
    the module docstring; nothing here is measured from the audio.
    """
    words = cue.text.split()
    if not words:
        return []
    weights = [max(len(w), 1) for w in words]
    total = sum(weights)
    span = cue.end - cue.start
    out, t = [], cue.start
    for w, weight in zip(words, weights):
        nxt = t + span * weight / total
        out.append(Word(text=w, start=t, end=nxt))
        t = nxt
    out[-1].end = cue.end          # absorb float drift onto the cue end
    return out


# --------------------------------------------------------------------------
# ASS generation
# --------------------------------------------------------------------------

def escape_ass(text):
    """Escape the characters that are special inside ASS dialogue text.

    ``\\`` introduces override codes (\\N, \\h) and ``{...}`` opens an
    override block, so a literal backslash or brace in a caption would
    corrupt the styling — they are escaped as \\\\, \\{, \\}. Commas
    need NO escaping: the Dialogue Text field is the last field, so
    commas inside caption text are legal and are preserved verbatim.
    """
    return (text.replace("\\", "\\\\")
                .replace("{", "\\{")
                .replace("}", "\\}"))


def ass_time(seconds):
    """Seconds -> ASS timestamp H:MM:SS.cc (centiseconds)."""
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, c = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def _style_line(name, spec):
    return (f"Style: {spec['ass_name']},Arial,{spec['fontsize']},"
            f"{spec['primary']},{spec['secondary']},{OUTLINE_COLOUR},"
            f"{SHADOW_COLOUR},-1,0,0,0,100,100,0,0,1,{spec['outline']},"
            f"{spec['shadow']},2,60,60,{spec['margin_v']},1")


def _pop_events(cue):
    """One event per word; the active word is accented + scaled."""
    words = split_words(cue)
    events = []
    for i, word in enumerate(words):
        end = words[i + 1].start if i + 1 < len(words) else cue.end
        parts = []
        for j, w in enumerate(words):
            piece = escape_ass(w.text)
            if j == i:
                piece = (f"{{\\1c{ACCENT}\\fscx{POP_SCALE}"
                         f"\\fscy{POP_SCALE}}}{piece}{{\\r}}")
            parts.append(piece)
        events.append((word.start, end, "Pop", " ".join(parts)))
    return events


def _karaoke_events(cue):
    """One event per cue; \\kf sweeps each word grey -> accent."""
    words = split_words(cue)
    segments = []
    for i, w in enumerate(words):
        cs = max(int(round((w.end - w.start) * 100)), 1)
        seg = f"{{\\kf{cs}}}{escape_ass(w.text)}"
        if i < len(words) - 1:
            seg += " "            # the space rides the previous word
        segments.append(seg)
    return [(cue.start, cue.end, "Karaoke", "".join(segments))]


def _clean_events(cue):
    """One plain event per cue; the author's line breaks are kept."""
    text = "\\N".join(escape_ass(ln) for ln in cue.text.split("\n"))
    return [(cue.start, cue.end, "Clean", text)]


_EVENT_BUILDERS = {"pop": _pop_events, "karaoke": _karaoke_events,
                   "clean": _clean_events}


def build_ass(cues, style):
    """Build the full styled .ass document. Returns (text, stats)."""
    if style not in STYLES:
        raise ToolError(f"unknown style: {style}")
    spec = STYLES[style]
    lines = [
        "[Script Info]",
        f"Title: {TOOL} — {style} captions",
        "ScriptType: v4.00+",
        f"PlayResX: {PLAY_RES_X}",
        f"PlayResY: {PLAY_RES_Y}",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, "
        "SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
        "MarginV, Encoding",
        _style_line(style, spec),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text",
    ]
    build = _EVENT_BUILDERS[style]
    events, word_count = [], 0
    for cue in cues:
        word_count += len(cue.text.split())
        events.extend(build(cue))
    for start, end, style_name, text in events:
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},"
                     f"{style_name},,0,0,0,,{text}")
    stats = {"events": len(events), "words": word_count,
             "style_name": spec["ass_name"]}
    return "\n".join(lines) + "\n", stats


# --------------------------------------------------------------------------
# ffmpeg / ffprobe — burn-in only; --ass-only never touches them
# --------------------------------------------------------------------------

def _run(cmd, timeout=RENDER_TIMEOUT):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def probe_video(path):
    """Return dict(duration, width, height, has_audio) or ToolError."""
    r = _run(["ffprobe", "-v", "error", "-show_entries",
              "stream=codec_type,width,height",
              "-show_entries", "format=duration",
              "-of", "json", str(path)], timeout=60)
    if r is None or r.returncode != 0:
        raise ToolError(f"ffprobe could not read {path.name} — "
                        "the file may be corrupt or not a video")
    try:
        data = json.loads(r.stdout)
    except (ValueError, TypeError):
        raise ToolError(f"ffprobe returned unreadable data for "
                        f"{path.name} — the file may be corrupt or "
                        "not a video")
    streams = data.get("streams") or []
    video = next((s for s in streams
                  if s.get("codec_type") == "video"), None)
    if video is None:
        raise ToolError(f"no video stream found in {path.name} — "
                        "not a video file this tool can caption")
    try:
        width, height = int(video["width"]), int(video["height"])
    except (KeyError, ValueError, TypeError):
        raise ToolError(f"could not read frame size from {path.name}")
    try:
        duration = float((data.get("format") or {}).get("duration"))
    except (ValueError, TypeError):
        duration = None
    if not duration or duration <= 0:
        raise ToolError(f"could not read a positive duration from "
                        f"{path.name} — the file may be corrupt")
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return {"duration": duration, "width": width, "height": height,
            "has_audio": has_audio}


def _filter_escape(path):
    """Escape a file path for use inside ffmpeg's subtitles= filter."""
    return (path.replace("\\", "\\\\")
                .replace(":", "\\:")
                .replace("'", "\\'"))


def burn_in(video, ass_text, out):
    """Render `out` = video + burned-in captions from `ass_text`.

    The styled .ass is written to a temp file and handed to the
    subtitles filter by path — an explicit styled file, because the
    filter silently ignores force_style. A failed render removes any
    partial output: this tool never leaves a fake success behind.
    """
    tmpdir = tempfile.mkdtemp(prefix="shorts-caption-studio-")
    ass_path = Path(tmpdir) / "captions.ass"
    try:
        ass_path.write_text(ass_text, encoding="utf-8")
        vf = f"subtitles='{_filter_escape(str(ass_path))}'"
        r = _run(["ffmpeg", "-y", "-i", str(video), "-vf", vf,
                  "-c:a", "copy", str(out)])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if r is None:
        raise ToolError("ffmpeg could not run or timed out — "
                        "nothing was rendered")
    if r.returncode != 0:
        if out.exists():
            out.unlink()
        tail = [ln.strip() for ln in (r.stderr or "").splitlines()
                if ln.strip()]
        hint = f" ({tail[-1][:160]})" if tail else ""
        raise ToolError(f"ffmpeg failed to render (exit "
                        f"{r.returncode}){hint} — no output produced")
    if not out.is_file() or out.stat().st_size == 0:
        raise ToolError("ffmpeg reported success but produced no "
                        "output file — refusing to call that a render")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class _JsonAwareParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as JSON in --json mode
    ({"error": ...} on stdout, same exit code 2) — an agent driving
    this tool with --json never gets plain text or a traceback."""

    json_mode = False

    def error(self, message):
        if self.json_mode:
            print(json.dumps({"error": message}))
            self.exit(2)
        super().error(message)


def _load_cues(path):
    """Read + parse an SRT file -> (cues, skipped) or ToolError."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="strict")
    except (OSError, UnicodeDecodeError) as exc:
        raise ToolError(f"could not read captions file: {path} "
                        f"({exc.__class__.__name__})")
    return parse_srt_text(text)


def _no_cues_error(name, skipped):
    if skipped:
        return (f"no usable caption events in {name} — every timed "
                f"cue was skipped ({len(skipped)} skipped: "
                + ", ".join(s["reason"] for s in skipped) + ")")
    return (f"no caption events parsed from {name} — is it an SRT "
            "file with timing lines?")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    ap = _JsonAwareParser(
        description="shorts-caption-studio — burn animated "
                    "word-highlight captions into vertical video "
                    "(or emit the styled .ass sidecar)")
    ap.json_mode = "--json" in argv
    ap.add_argument("video", nargs="?",
                    help="video file to burn captions into")
    ap.add_argument("--captions",
                    help="SRT transcript to burn in (required with a "
                         "video)")
    ap.add_argument("--ass-only", metavar="SRT",
                    help="emit the styled .ass for this SRT and exit "
                         "(no video, no ffmpeg needed)")
    ap.add_argument("-o", "--out",
                    help="output file (burn-in default: "
                         "<video>.captioned.mp4 beside the video; "
                         "required with --ass-only)")
    ap.add_argument("--style", choices=sorted(STYLES), default="pop",
                    help="caption style (default: pop)")
    ap.add_argument("--json", action="store_true",
                    help="print one JSON object instead of the "
                         "human-readable report")
    a = ap.parse_args(argv)

    def fail(msg):
        # The same clean error in both modes: plain "ERROR: ..." for a
        # human, {"error": ...} for an agent — exit 2 either way.
        if a.json:
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}")
        return 2

    if a.ass_only and a.video:
        return fail("pass either a video to burn into or --ass-only "
                    "SRT to emit a sidecar, not both")
    if not a.ass_only and not a.video:
        return fail("nothing to do: pass a video file (with "
                    "--captions SRT) or --ass-only SRT -o OUT.ass")

    warnings = []

    # ---------------- --ass-only mode (pure Python) ----------------
    if a.ass_only:
        if a.captions:
            return fail("--captions is not used with --ass-only; the "
                        "SRT is the --ass-only argument")
        if not a.out:
            return fail("-o OUT.ass is required with --ass-only")
        srt = Path(a.ass_only)
        if not srt.is_file():
            return fail(f"captions file not found: {srt}")
        out = Path(a.out)
        if out.resolve() == srt.resolve():
            return fail("output would overwrite the input captions "
                        "file — choose a different -o")
        try:
            cues, skipped = _load_cues(srt)
        except ToolError as e:
            return fail(str(e))
        if not cues:
            return fail(_no_cues_error(srt.name, skipped))
        ass_text, stats = build_ass(cues, a.style)
        try:
            out.write_text(ass_text, encoding="utf-8")
        except OSError:
            return fail(f"could not write output file: {out}")
        for s in skipped:
            warnings.append(f"cue #{s['index']} skipped "
                            f"({s['reason']}: {s['detail']})")
        payload = {
            "tool": TOOL, "version": VERSION, "command": "ass-only",
            "captions": srt.name, "style": a.style,
            "output_file": str(out), "cue_count": len(cues),
            "word_count": stats["words"],
            "event_count": stats["events"],
            "word_timing": "estimated",
            "skipped_cues": skipped, "warnings": warnings,
        }
        if a.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"{TOOL} v{VERSION} — ass-only")
            print(f"Captions: {srt.name} — {len(cues)} cues, "
                  f"{stats['words']} words")
            print(f"Style: {a.style} ({STYLES[a.style]['blurb']}) · "
                  f"PlayRes {PLAY_RES_X}x{PLAY_RES_Y}")
            print("Word timing: ESTIMATED (cue duration split by "
                  "word length — not true word alignment)")
            print(f"ASS written: {out} ({stats['events']} events)")
            for w in warnings:
                print(f"  WARN: {w}")
        return 1 if warnings else 0

    # ---------------- burn-in mode (ffmpeg) ----------------
    video = Path(a.video)
    if not video.is_file():
        return fail(f"file not found: {video}")
    if not a.captions:
        return fail("--captions SRT is required — the transcript "
                    "to burn in")
    cap = Path(a.captions)
    if not cap.is_file():
        return fail(f"captions file not found: {cap}")
    missing = [t for t in ("ffmpeg", "ffprobe")
               if shutil.which(t) is None]
    if missing:
        return fail(f"{' and '.join(missing)} not found on PATH — "
                    "burn-in needs FFmpeg to render. Install FFmpeg "
                    "and re-run, or use --ass-only to emit the styled "
                    ".ass without it. Nothing was rendered.")
    try:
        info = probe_video(video)
    except ToolError as e:
        return fail(str(e))
    try:
        cues, skipped = _load_cues(cap)
    except ToolError as e:
        return fail(str(e))
    if not cues:
        return fail(_no_cues_error(cap.name, skipped))
    if a.out:
        out = Path(a.out)
        if out.resolve() == video.resolve():
            return fail("output would overwrite the input video — "
                        "choose a different --out")
    else:
        out = video.with_name(video.stem + ".captioned.mp4")
    for s in skipped:
        warnings.append(f"cue #{s['index']} skipped "
                        f"({s['reason']}: {s['detail']})")
    if info["height"] <= info["width"]:
        warnings.append(f"video is not vertical ({info['width']}x"
                        f"{info['height']}) — the styles are tuned "
                        f"for {PLAY_RES_X}x{PLAY_RES_Y} vertical")
    last_end = max(c.end for c in cues)
    if last_end > info["duration"] + 0.25:
        warnings.append(f"captions run to {last_end:.1f}s but the "
                        f"video is {info['duration']:.1f}s — the "
                        "tail captions will not be seen")
    ass_text, stats = build_ass(cues, a.style)
    try:
        burn_in(video, ass_text, out)
    except ToolError as e:
        return fail(str(e))
    payload = {
        "tool": TOOL, "version": VERSION, "command": "render",
        "video": video.name, "path": str(video),
        "captions": cap.name, "style": a.style,
        "output_file": str(out),
        "width": info["width"], "height": info["height"],
        "duration_seconds": round(info["duration"], 3),
        "has_audio": info["has_audio"],
        "cue_count": len(cues), "word_count": stats["words"],
        "event_count": stats["events"],
        "word_timing": "estimated",
        "skipped_cues": skipped, "warnings": warnings,
    }
    if a.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"{TOOL} v{VERSION} — render")
        print(f"Video: {video.name} ({info['width']}x"
              f"{info['height']}, {info['duration']:.1f}s)")
        print(f"Captions: {cap.name} — {len(cues)} cues, "
              f"{stats['words']} words")
        print(f"Style: {a.style} ({STYLES[a.style]['blurb']}) · "
              f"PlayRes {PLAY_RES_X}x{PLAY_RES_Y}")
        print("Word timing: ESTIMATED (cue duration split by word "
              "length — not true word alignment)")
        print(f"Rendered: {out} ({stats['events']} caption events "
              "burned in)")
        for w in warnings:
            print(f"  WARN: {w}")
    return 1 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
