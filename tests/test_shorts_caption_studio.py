#!/usr/bin/env python3
"""Tests for shorts-caption-studio. Stdlib unittest only.

Run from the pack root:
    python3 -m unittest discover -s tests -v

Unit tests cover the ASS generation (estimated word-split timing math,
style blocks, escaping), the SRT parser's skipped-cue reporting, and
the CLI's error paths — both directions, clean errors, no tracebacks.
The integration tests use real ffmpeg (they SKIP, never fake-pass,
when ffmpeg is absent) to burn captions into a generated 3-second
vertical video and probe the result.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
SRC = PACK_ROOT / "src" / "shorts_caption_studio.py"
EXAMPLES = PACK_ROOT / "examples"
sys.path.insert(0, str(PACK_ROOT / "src"))

import shorts_caption_studio as scs  # noqa: E402

BASIC_SRT = """1
00:00:00,000 --> 00:00:02,000
Hello world

2
00:00:02,000 --> 00:00:04,000
Second cue here
"""

MESSY_SRT = """1
00:00:00,000 --> 00:00:02,000
Good cue

2
00:00:02,000 --> 00:00:03,000

3
00:00:03,000 --> 00:00:02,500
Backwards cue
"""


def run_cli(*argv, cwd=None, env=None):
    return subprocess.run(
        [sys.executable, str(SRC), *argv],
        capture_output=True, text=True, cwd=cwd or PACK_ROOT, env=env)


def make_cue(text, start=0.0, end=4.0, index=1):
    return scs.Cue(index=index, start=start, end=end, text=text)


def dialogue_lines(ass_text):
    return [ln for ln in ass_text.splitlines()
            if ln.startswith("Dialogue:")]


def dialogue_text(line):
    # Text is the 10th field; split at most 9 commas so commas inside
    # the caption text itself survive the round trip.
    return line.split(",", 9)[9]


# ---------------------------------------------------------------------------
# estimated word timing
# ---------------------------------------------------------------------------

class WordSplitTests(unittest.TestCase):
    def test_equal_length_words_split_evenly(self):
        words = scs.split_words(make_cue("aa bb cc dd", 0.0, 4.0))
        self.assertEqual([(w.start, w.end) for w in words],
                         [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0),
                          (3.0, 4.0)])

    def test_split_is_proportional_to_word_length(self):
        words = scs.split_words(make_cue("a bbb", 0.0, 4.0))
        self.assertAlmostEqual(words[0].end - words[0].start, 1.0)
        self.assertAlmostEqual(words[1].end - words[1].start, 3.0)
        self.assertAlmostEqual(words[1].start, 1.0)

    def test_single_word_gets_the_whole_cue(self):
        words = scs.split_words(make_cue("Solo", 1.5, 3.25))
        self.assertEqual(len(words), 1)
        self.assertEqual((words[0].start, words[0].end), (1.5, 3.25))

    def test_last_word_ends_exactly_at_cue_end(self):
        words = scs.split_words(make_cue("a bb ccc dddd", 0.0, 3.3))
        self.assertEqual(words[-1].end, 3.3)
        for prev, nxt in zip(words, words[1:]):
            self.assertEqual(prev.end, nxt.start)

    def test_words_keep_text_and_order(self):
        words = scs.split_words(make_cue("one two\nthree", 0.0, 3.0))
        self.assertEqual([w.text for w in words],
                         ["one", "two", "three"])


# ---------------------------------------------------------------------------
# ASS formatting & escaping
# ---------------------------------------------------------------------------

class AssFormatTests(unittest.TestCase):
    def test_ass_time_zero(self):
        self.assertEqual(scs.ass_time(0), "0:00:00.00")

    def test_ass_time_minutes_and_centiseconds(self):
        self.assertEqual(scs.ass_time(61.25), "0:01:01.25")
        self.assertEqual(scs.ass_time(9.999), "0:00:10.00")

    def test_ass_time_hours(self):
        self.assertEqual(scs.ass_time(3661.5), "1:01:01.50")

    def test_escape_braces_and_backslash(self):
        self.assertEqual(scs.escape_ass(r"a{b}c\d"),
                         r"a\{b\}c\\d")

    def test_escape_leaves_plain_text_alone(self):
        self.assertEqual(scs.escape_ass("plain words only"),
                         "plain words only")

    def test_comma_is_preserved_and_survives_field_split(self):
        # The Dialogue Text field is last, so commas in caption text
        # are legal ASS — the generator must not mangle them.
        cue = make_cue("Wait, really, yes", 0.0, 2.0)
        ass, _ = scs.build_ass([cue], "clean")
        line = dialogue_lines(ass)[0]
        self.assertEqual(dialogue_text(line), "Wait, really, yes")

    def test_header_is_vertical_playres(self):
        ass, _ = scs.build_ass([make_cue("Hi there")], "pop")
        self.assertIn("PlayResX: 1080", ass)
        self.assertIn("PlayResY: 1920", ass)
        self.assertIn("ScriptType: v4.00+", ass)


# ---------------------------------------------------------------------------
# styles & event generation
# ---------------------------------------------------------------------------

class StyleTests(unittest.TestCase):
    def test_every_style_keeps_text_out_of_shorts_bottom_ui(self):
        for name, spec in scs.STYLES.items():
            self.assertGreaterEqual(
                spec["margin_v"], scs.SHORTS_BOTTOM_UI_PX,
                f"{name} MarginV {spec['margin_v']} intrudes into "
                "the Shorts bottom UI zone")
            ass, _ = scs.build_ass([make_cue("Hi there")], name)
            self.assertIn(f"Style: {spec['ass_name']},", ass)

    def test_pop_one_event_per_word_with_active_highlight(self):
        cue = make_cue("one two three", 0.0, 3.0)
        ass, stats = scs.build_ass([cue], "pop")
        lines = dialogue_lines(ass)
        self.assertEqual(len(lines), 3)
        self.assertEqual(stats["events"], 3)
        first = dialogue_text(lines[0])
        self.assertIn(scs.ACCENT, first)
        self.assertIn("\\fscx120", first)
        # the highlight opens the line: word 1 is the active one
        self.assertTrue(first.startswith("{\\1c"))

    def test_pop_second_event_highlights_second_word(self):
        cue = make_cue("one two three", 0.0, 3.0)
        ass, _ = scs.build_ass([cue], "pop")
        second = dialogue_text(dialogue_lines(ass)[1])
        plain_one, rest = second.split(" ", 1)
        self.assertEqual(plain_one, "one")          # no longer active
        self.assertTrue(rest.startswith("{\\1c"))   # "two" is active
        self.assertIn("two", rest)

    def test_pop_events_tile_the_cue(self):
        cue = make_cue("aa bb", 1.0, 3.0)
        ass, _ = scs.build_ass([cue], "pop")
        lines = dialogue_lines(ass)
        self.assertIn(",0:00:01.00,0:00:02.00,", lines[0])
        self.assertIn(",0:00:02.00,0:00:03.00,", lines[1])

    def test_karaoke_single_event_and_kf_durations_sum_to_cue(self):
        cue = make_cue("aa bbbb cc", 0.0, 4.0)
        ass, stats = scs.build_ass([cue], "karaoke")
        lines = dialogue_lines(ass)
        self.assertEqual(len(lines), 1)
        self.assertEqual(stats["events"], 1)
        durations = [int(x) for x in
                     re.findall(r"\\kf(\d+)", dialogue_text(lines[0]))]
        self.assertEqual(len(durations), 3)
        self.assertAlmostEqual(sum(durations), 400, delta=3)

    def test_karaoke_style_fills_grey_to_accent(self):
        ass, _ = scs.build_ass([make_cue("Hi there")], "karaoke")
        style_line = [ln for ln in ass.splitlines()
                      if ln.startswith("Style: Karaoke")][0]
        self.assertIn(scs.ACCENT, style_line)          # filled colour
        self.assertIn(scs.KARAOKE_UNFILLED, style_line)

    def test_clean_single_event_no_highlight_line_break_kept(self):
        cue = make_cue("First line\nSecond line", 0.0, 2.0)
        ass, stats = scs.build_ass([cue], "clean")
        lines = dialogue_lines(ass)
        self.assertEqual(len(lines), 1)
        self.assertEqual(stats["events"], 1)
        text = dialogue_text(lines[0])
        self.assertEqual(text, "First line\\NSecond line")
        self.assertNotIn("\\kf", text)
        self.assertNotIn(scs.ACCENT, text)
        self.assertNotIn("{", text)


# ---------------------------------------------------------------------------
# SRT parsing
# ---------------------------------------------------------------------------

class ParserTests(unittest.TestCase):
    def test_parse_basic_srt(self):
        cues, skipped = scs.parse_srt_text(BASIC_SRT)
        self.assertEqual(len(cues), 2)
        self.assertEqual(skipped, [])
        self.assertEqual(cues[0].text, "Hello world")
        self.assertEqual((cues[1].start, cues[1].end), (2.0, 4.0))

    def test_empty_cue_is_skipped_and_reported(self):
        cues, skipped = scs.parse_srt_text(MESSY_SRT)
        self.assertEqual([c.text for c in cues], ["Good cue"])
        reasons = {s["index"]: s["reason"] for s in skipped}
        self.assertEqual(reasons[2], "empty-text")

    def test_invalid_timing_is_skipped_and_reported(self):
        _, skipped = scs.parse_srt_text(MESSY_SRT)
        reasons = {s["index"]: s["reason"] for s in skipped}
        self.assertEqual(reasons[3], "invalid-timing")

    def test_garbage_parses_to_nothing(self):
        cues, skipped = scs.parse_srt_text("not a subtitle file\n"
                                           "just some words\n")
        self.assertEqual(cues, [])
        self.assertEqual(skipped, [])

    def test_html_tags_are_stripped_from_text(self):
        cues, _ = scs.parse_srt_text(
            "1\n00:00:00,000 --> 00:00:01,000\n<i>Styled</i> words\n")
        self.assertEqual(cues[0].text, "Styled words")


# ---------------------------------------------------------------------------
# CLI error paths & warnings (subprocess — real exit codes)
# ---------------------------------------------------------------------------

class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scs-test-"))
        self.srt = self.tmp / "ok.srt"
        self.srt.write_text(BASIC_SRT, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_video_is_clean_error(self):
        r = run_cli(str(self.tmp / "nope.mp4"),
                    "--captions", str(self.srt))
        self.assertEqual(r.returncode, 2)
        self.assertIn("ERROR: file not found", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_missing_captions_file_is_clean_error(self):
        video = self.tmp / "v.mp4"
        video.write_bytes(b"x")
        r = run_cli(str(video), "--captions",
                    str(self.tmp / "nope.srt"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("ERROR: captions file not found", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_burn_in_requires_captions_flag(self):
        video = self.tmp / "v.mp4"
        video.write_bytes(b"x")
        r = run_cli(str(video))
        self.assertEqual(r.returncode, 2)
        self.assertIn("--captions SRT is required", r.stdout)

    def test_ass_only_requires_out(self):
        r = run_cli("--ass-only", str(self.srt))
        self.assertEqual(r.returncode, 2)
        self.assertIn("-o OUT.ass is required", r.stdout)

    def test_video_and_ass_only_together_is_error(self):
        r = run_cli("v.mp4", "--ass-only", str(self.srt),
                    "-o", str(self.tmp / "x.ass"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("not both", r.stdout)

    def test_no_arguments_is_clean_error(self):
        r = run_cli()
        self.assertEqual(r.returncode, 2)
        self.assertIn("ERROR: nothing to do", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_unparseable_srt_is_clean_error(self):
        bad = self.tmp / "bad.srt"
        bad.write_text("hello\nthis is not subtitles\n",
                       encoding="utf-8")
        r = run_cli("--ass-only", str(bad),
                    "-o", str(self.tmp / "x.ass"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("no caption events parsed", r.stdout)
        self.assertFalse((self.tmp / "x.ass").exists())

    def test_ass_only_refuses_to_overwrite_input(self):
        r = run_cli("--ass-only", str(self.srt), "-o", str(self.srt))
        self.assertEqual(r.returncode, 2)
        self.assertIn("overwrite the input", r.stdout)

    def test_skipped_cues_warn_and_exit_1_but_still_write(self):
        messy = self.tmp / "messy.srt"
        messy.write_text(MESSY_SRT, encoding="utf-8")
        out = self.tmp / "messy.ass"
        r = run_cli("--ass-only", str(messy), "-o", str(out))
        self.assertEqual(r.returncode, 1)
        self.assertIn("WARN: cue #2 skipped (empty-text", r.stdout)
        self.assertIn("WARN: cue #3 skipped (invalid-timing",
                      r.stdout)
        self.assertTrue(out.is_file())

    def test_bad_style_choice_is_clean_usage_error(self):
        r = run_cli("--ass-only", str(self.srt), "-o",
                    str(self.tmp / "x.ass"), "--style", "neon")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# --json conventions
# ---------------------------------------------------------------------------

class JsonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scs-json-"))
        self.srt = self.tmp / "ok.srt"
        self.srt.write_text(BASIC_SRT, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ass_only_json_shape(self):
        out = self.tmp / "x.ass"
        r = run_cli("--ass-only", str(self.srt), "-o", str(out),
                    "--style", "karaoke", "--json")
        self.assertEqual(r.returncode, 0)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["tool"], "shorts-caption-studio")
        self.assertEqual(payload["version"], scs.VERSION)
        self.assertEqual(payload["command"], "ass-only")
        self.assertEqual(payload["style"], "karaoke")
        self.assertEqual(payload["cue_count"], 2)
        self.assertEqual(payload["word_count"], 5)
        self.assertEqual(payload["event_count"], 2)
        # the honesty field: timing is estimated, never "aligned"
        self.assertEqual(payload["word_timing"], "estimated")
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(payload["skipped_cues"], [])

    def test_json_error_object_on_missing_file(self):
        r = run_cli("--ass-only", str(self.tmp / "nope.srt"),
                    "-o", str(self.tmp / "x.ass"), "--json")
        self.assertEqual(r.returncode, 2)
        payload = json.loads(r.stdout)
        self.assertIn("error", payload)
        self.assertIn("not found", payload["error"])

    def test_json_usage_error_is_json_object(self):
        r = run_cli("--json")
        self.assertEqual(r.returncode, 2)
        payload = json.loads(r.stdout)
        self.assertIn("error", payload)

    def test_json_and_text_agree_on_counts(self):
        out = self.tmp / "x.ass"
        rj = run_cli("--ass-only", str(self.srt), "-o", str(out),
                     "--json")
        payload = json.loads(rj.stdout)
        ass = out.read_text(encoding="utf-8")
        self.assertEqual(len(dialogue_lines(ass)),
                         payload["event_count"])


# ---------------------------------------------------------------------------
# ffmpeg absent — burn-in fails clean, --ass-only does not care
# ---------------------------------------------------------------------------

class NoFfmpegTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scs-noffmpeg-"))
        self.srt = self.tmp / "ok.srt"
        self.srt.write_text(BASIC_SRT, encoding="utf-8")
        self.empty_bin = self.tmp / "bin"
        self.empty_bin.mkdir()
        self.env = dict(os.environ, PATH=str(self.empty_bin))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_burn_in_without_ffmpeg_is_clean_error(self):
        video = self.tmp / "v.mp4"
        video.write_bytes(b"x")
        r = run_cli(str(video), "--captions", str(self.srt),
                    env=self.env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("not found on PATH", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_ass_only_works_without_ffmpeg(self):
        out = self.tmp / "x.ass"
        r = run_cli("--ass-only", str(self.srt), "-o", str(out),
                    env=self.env)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(out.is_file())


# ---------------------------------------------------------------------------
# real ffmpeg integration — generate, burn, probe
# ---------------------------------------------------------------------------

@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "ffmpeg/ffprobe not on PATH")
class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scs-it-"))
        self.video = self.tmp / "clip.mp4"
        gen = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             "color=c=0x336699:s=720x1280:r=30:d=3",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
             str(self.video)],
            capture_output=True, text=True)
        if gen.returncode != 0:
            self.skipTest("could not generate the test video")
        self.srt = self.tmp / "clip.srt"
        self.srt.write_text(
            "1\n00:00:00,000 --> 00:00:01,500\nBurn these words in\n"
            "\n2\n00:00:01,500 --> 00:00:03,000\nSecond cue follows\n",
            encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def probe(self, path):
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,width,height",
             "-show_entries", "format=duration", "-of", "json",
             str(path)], capture_output=True, text=True)
        return json.loads(r.stdout)

    def test_burn_in_produces_real_video_at_same_size(self):
        out = self.tmp / "clip.captioned.mp4"
        r = run_cli(str(self.video), "--captions", str(self.srt),
                    "--style", "pop")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Rendered:", r.stdout)
        self.assertTrue(out.is_file())
        self.assertGreater(out.stat().st_size, 0)
        data = self.probe(out)
        stream = data["streams"][0]
        self.assertEqual((stream["width"], stream["height"]),
                         (720, 1280))
        self.assertAlmostEqual(
            float(data["format"]["duration"]), 3.0, delta=0.4)

    def test_burn_in_json_reports_measured_facts(self):
        r = run_cli(str(self.video), "--captions", str(self.srt),
                    "--style", "karaoke", "--json")
        self.assertEqual(r.returncode, 0, r.stdout)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["command"], "render")
        self.assertEqual((payload["width"], payload["height"]),
                         (720, 1280))
        self.assertEqual(payload["cue_count"], 2)
        self.assertEqual(payload["word_timing"], "estimated")
        self.assertTrue(Path(payload["output_file"]).is_file())

    def test_non_video_input_is_clean_error(self):
        fake = self.tmp / "fake.mp4"
        fake.write_text("this is not a video", encoding="utf-8")
        r = run_cli(str(fake), "--captions", str(self.srt))
        self.assertEqual(r.returncode, 2)
        self.assertIn("ERROR:", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
