"""v0.2 behaviour: candidate scan vs final pack, detail command, transcript confidence, retention.

All inputs are synthetic (tests/fixtures.py). These tests check local behaviour only; they say nothing
about how well Claude answers questions about a video.
"""
import functools
import http.server
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import fixtures  # noqa: E402
import watch  # noqa: E402

WATCH = ROOT / "watch.py"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="watch-v02-"))
        cls.vids = {}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def fixture(self, name):
        if name not in self.vids:
            self.vids[name] = fixtures.ALL[name](self.base)
        return self.vids[name]

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=self.base))

    def watch(self, *args):
        env = {**os.environ, "TEMP": str(self.tmp), "TMP": str(self.tmp), "TMPDIR": str(self.tmp),
               "HF_HUB_DISABLE_SYMLINKS_WARNING": "1"}
        return subprocess.run([sys.executable, str(WATCH), *map(str, args)], capture_output=True, text=True, env=env)

    def analyze(self, name, *args):
        video, events = self.fixture(name)
        r = self.watch(video, "--no-audio", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        wd = Path(next(l[9:] for l in r.stdout.splitlines() if l.startswith("workdir: ")))
        return wd, json.loads((wd / "manifest.json").read_text(encoding="utf-8")), events, r

    def manifest(self, wd):
        return json.loads((wd / "manifest.json").read_text(encoding="utf-8"))


class EventTests(Base):
    """Detection in the scan and presence in the final pack are measured separately."""

    def check(self, name, must_be_in_pack):
        wd, m, events, _ = self.analyze(name)
        sheets = [Path(s["path"]) for s in m["sheets"]]
        for e in events:
            detected = [c for c in m["candidates"] if e["t0"] <= c["t"] <= e["t1"]]
            self.assertTrue(detected, f"{name}: event {e} not detected by the scan")
            in_pack = any(fixtures.color_pixels(p, e["color"]) >= 4 for p in sheets)
            reported = any(o["t0"] <= c["t"] <= o["t1"] for o in m["omitted"] for c in detected)
            # never a silent loss: either shown, or reported as an omitted interval Claude can ask for
            self.assertTrue(in_pack or reported, f"{name}: event neither shown nor reported")
            if must_be_in_pack:
                self.assertTrue(in_pack, f"{name}: event detected but not in the final pack")
        self.assertLessEqual(len(m["shown"]), watch.OVERVIEW_CAP)

    def test_flash_at_three_times(self):
        for n in ("flash_02", "flash_14", "flash_27"):
            with self.subTest(n):
                self.check(n, must_be_in_pack=True)

    def test_small_change(self):
        self.check("small_change", must_be_in_pack=True)

    def test_busy_videos_never_lose_events_silently(self):
        # no in-pack guarantee here: with more candidates than the cap, only "shown or reported" is promised
        for n in ("noise_03", "noise_14", "noise_26", "scroll_04", "scroll_20", "scroll_28",
                  "long_005", "long_095", "long_170"):
            with self.subTest(n):
                self.check(n, must_be_in_pack=False)

    def test_static_screen_shows_few_frames(self):
        wd, m, _, _ = self.analyze("static")
        self.assertLessEqual(len(m["shown"]), 4)
        self.assertEqual(len(m["sheets"]), 1)

    def test_images_respect_own_edge_budget(self):
        for n in ("static", "long_095", "small_text"):
            wd, m, _, _ = self.analyze(n)
            for s in m["sheets"]:
                w, h = fixtures.png_size(Path(s["path"]))
                self.assertLessEqual(max(w, h), watch.EDGE)
                self.assertEqual((w, h), (s["width"], s["height"]))


class SelectionUnitTests(unittest.TestCase):
    def test_omitted_intervals_cover_every_unshown_candidate(self):
        rng = np.random.default_rng(0)
        cands = [{"t": i * 0.2, "kind": "change", "score": float(rng.integers(12, 255)), "bbox": None} for i in range(200)]
        thumbs = [rng.integers(0, 255, (20, 30, 3), dtype=np.uint8) for _ in cands]
        shown = watch.select(cands, thumbs, 24)
        self.assertEqual(len(shown), 24)
        self.assertEqual(shown, sorted(shown))
        om = watch.omitted_intervals(cands, shown)
        self.assertEqual(sum(o["count"] for o in om), 200 - 24)
        for i, c in enumerate(cands):
            if i not in shown:
                self.assertTrue(any(o["t0"] <= c["t"] <= o["t1"] for o in om))

    def test_duplicates_are_shown_once(self):
        a = np.zeros((20, 30, 3), np.uint8)
        b = np.full((20, 30, 3), 255, np.uint8)
        c = a.copy()
        c[2:6, 2:6] = (255, 0, 0)
        thumbs = [a, b] * 20 + [c]
        cands = [{"t": float(i), "kind": "change", "score": 255.0, "bbox": None} for i in range(len(thumbs))]
        shown = watch.select(cands, thumbs, 3)
        self.assertIn(len(thumbs) - 1, shown)   # the one distinct frame wins over repeated states


class TranscriptUnitTests(unittest.TestCase):
    def seg(self, text, low):
        return {"start": 1.0, "end": 2.0, "text": text, "avg_logprob": -2.0 if low else -0.2,
                "no_speech_prob": 0.1, "compression_ratio": 1.2, "low_confidence": low}

    def test_uncertain_language_keeps_confident_text(self):
        tr = {"status": "ok", "vad": True, "language": "pt", "language_probability": 0.2,
              "audio_seconds": 10.0, "speech_seconds": 3.0, "segments": [self.seg("hello there", False)]}
        out = "\n".join(watch.render_transcript(tr, Path("X")))
        self.assertIn("hello there", out)
        self.assertIn("language uncertain", out)

    def test_low_confidence_is_reported_not_dropped(self):
        tr = {"status": "ok", "vad": True, "language": "en", "language_probability": 0.9,
              "audio_seconds": 10.0, "speech_seconds": 3.0, "segments": [self.seg("garbled", True)]}
        out = "\n".join(watch.render_transcript(tr, Path("X")))
        self.assertNotIn("garbled", out)
        self.assertIn("low-confidence segments not shown (1", out)
        self.assertIn("1.0-2.0s", out)
        self.assertIn("--transcript", out)

    def test_no_vad_speech_is_not_called_no_speech(self):
        tr = {"status": "ok", "vad": True, "language": "en", "language_probability": 0.4,
              "audio_seconds": 10.0, "speech_seconds": 0.0, "segments": []}
        out = "\n".join(watch.render_transcript(tr, Path("X")))
        self.assertIn("VAD can miss quiet speech", out)
        self.assertIn("--no-vad", out)


class TranscriptCommandTests(Base):
    def test_hidden_segments_can_be_reinspected(self):
        wd, m, _, _ = self.analyze("small_text")
        tr = {"status": "ok", "vad": True, "language": "en", "language_probability": 0.9, "audio_seconds": 10.0,
              "speech_seconds": 4.0, "segments": [
                  {"start": 1.0, "end": 2.0, "text": "clear words", "avg_logprob": -0.2, "no_speech_prob": 0.1,
                   "compression_ratio": 1.1, "low_confidence": False},
                  {"start": 5.0, "end": 6.0, "text": "unsure words", "avg_logprob": -1.5, "no_speech_prob": 0.2,
                   "compression_ratio": 1.1, "low_confidence": True}]}
        (wd / "transcript.json").write_text(json.dumps(tr), encoding="utf-8")
        default = self.watch("--transcript", wd)
        self.assertIn("clear words", default.stdout)
        self.assertNotIn("unsure words", default.stdout)
        full = self.watch("--transcript", wd, "--all", "--range", "4-7")
        self.assertIn("LOW-CONFIDENCE", full.stdout)
        self.assertIn("unsure words", full.stdout)
        self.assertNotIn("clear words", full.stdout)

    def test_silent_video_does_not_crash(self):
        video, _ = self.fixture("silent")
        r = self.watch(video)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no audio track", r.stdout)


class DetailTests(Base):
    def detail_files(self, wd):
        return sorted(wd.glob("detail_*.png")) + sorted(wd.glob("detail_tmp_*"))

    def test_detail_success_and_budget(self):
        wd, m, _, _ = self.analyze("small_text")
        r = self.watch("--detail", wd, "--range", "2-3", "--fps", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        files = sorted(wd.glob("detail_*.png"))
        self.assertEqual(len(files), 3)
        for f in files:
            self.assertLessEqual(max(fixtures.png_size(f)), watch.EDGE)
        c = self.watch("--detail", wd, "--range", "1-1", "--crop", "0.25,0.1,0.5,0.3")
        self.assertEqual(c.returncode, 0, c.stderr)
        crop = [f for f in wd.glob("detail_02_*.png")]
        self.assertEqual([fixtures.png_size(f) for f in crop], [(960, 324)])   # native crop, not upscaled
        b = self.manifest(wd)["detail"]
        self.assertEqual((b["calls"], b["images"]), (2, 4))

    def test_invalid_requests_change_nothing(self):
        wd, m, _, _ = self.analyze("small_text")
        before = self.manifest(wd)["detail"]
        bad = [["--range", "9-12"], ["--range", "3-2"], ["--range", "abc"], ["--range", "-1-2"],
               ["--range", "0-5", "--fps", "4"], ["--range", "1-2", "--fps", "0"], ["--range", "1-2", "--fps", "20"],
               ["--range", "1-2", "--crop", "0.9,0,0.2,0.1"], ["--range", "1-2", "--crop", "1,2,3"],
               ["--range", "1-2", "--crop", "0,0,0.001,0.001"], []]
        for args in bad:
            with self.subTest(args):
                r = self.watch("--detail", wd, *args)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(self.detail_files(wd), [])
                self.assertEqual(self.manifest(wd)["detail"], before)

    def test_budget_is_checked_before_writing(self):
        wd, m, _, _ = self.analyze("small_text")
        self.assertEqual(self.watch("--detail", wd, "--range", "0-3.5", "--fps", "2").returncode, 0)   # 8 images
        r = self.watch("--detail", wd, "--range", "5-5")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("budget", r.stderr)
        self.assertEqual(len(list(wd.glob("detail_*.png"))), 8)
        self.assertEqual(self.manifest(wd)["detail"]["images"], 8)
        self.assertEqual(self.watch("--detail", wd, "--range", "5-5", "--allow-more").returncode, 0)

    def test_changed_local_source_is_refused(self):
        video, _ = fixtures.small_text(self.tmp)       # private copy we may touch
        r = self.watch(video, "--no-audio")
        wd = Path(next(l[9:] for l in r.stdout.splitlines() if l.startswith("workdir: ")))
        st = video.stat()
        os.utime(video, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
        d = self.watch("--detail", wd, "--range", "1-2")
        self.assertNotEqual(d.returncode, 0)
        self.assertIn("changed", d.stderr)
        self.assertTrue(video.exists())

    def test_cleaned_workdir_is_refused(self):
        wd, m, _, _ = self.analyze("small_text")
        self.assertEqual(self.watch("--cleanup", wd).returncode, 0)
        r = self.watch("--detail", wd, "--range", "1-2")
        self.assertNotEqual(r.returncode, 0)

    def test_removed_interval_option_explains_itself(self):
        video, _ = self.fixture("silent")
        r = self.watch(video, "--interval", "1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--interval was removed in v0.2", r.stderr)
        self.assertIn("--detail", r.stderr)
        self.assertEqual(list(self.tmp.glob("video-watch-*")), [])

    def test_retain_source_requires_download(self):
        video, _ = self.fixture("small_text")
        r = self.watch(video, "--retain-source")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(list(self.tmp.glob("video-watch-*")), [])


@unittest.skipUnless(importlib.util.find_spec("yt_dlp"), "yt-dlp not installed (optional dependency)")
class DownloadRetentionTests(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.video, _ = fixtures.small_text(cls.base)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(cls.base))
        handler.log_message = lambda *a: None
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/{cls.video.name}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        super().tearDownClass()

    def run_download(self, *args):
        r = self.watch("--download", self.url, "--no-audio", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return Path(next(l[9:] for l in r.stdout.splitlines() if l.startswith("workdir: "))), r

    def test_default_deletes_download_and_detail_is_refused(self):
        wd, r = self.run_download()
        self.assertFalse((wd / "video.mp4").exists())
        d = self.watch("--detail", wd, "--range", "1-2")
        self.assertNotEqual(d.returncode, 0)
        self.assertIn("--retain-source", d.stderr)

    def test_retain_source_until_cleanup(self):
        wd, r = self.run_download("--retain-source")
        self.assertIn("RETAINED", r.stdout)
        self.assertTrue((wd / "video.mp4").exists())
        self.assertEqual(self.watch("--detail", wd, "--range", "1-2").returncode, 0)
        self.assertEqual(self.watch("--cleanup", wd).returncode, 0)
        self.assertFalse(wd.exists())


class RetentionTests(Base):
    def test_stale_sweep_skips_keep_dirs_and_only_runs_on_a_new_analysis(self):
        keep, *_ = self.analyze("silent", "--keep")
        plain, *_ = self.analyze("silent")
        old = time.time() - watch.STALE_SECONDS - 60
        for d in (keep, plain):
            os.utime(d, (old, old))
        # a detail/transcript call does not sweep
        self.watch("--transcript", keep)
        self.assertTrue(plain.exists())
        self.analyze("silent")
        self.assertTrue(keep.exists(), "--keep dirs are only removed by --cleanup")
        self.assertFalse(plain.exists(), "stale dirs are removed at the start of the next analysis")

    def test_failure_mid_scan_still_removes_workdir(self):
        # regression: ffmpeg kept the scan log open after a Python error, so cleanup failed on Windows
        video, _ = self.fixture("noise_14")
        code = (f"import sys; sys.argv=['watch.py', {str(video)!r}, '--no-audio']; sys.path.insert(0, {str(ROOT)!r})\n"
                "import watch\nn = [0]\norig = watch.block_scores\n"
                "def boom(*a):\n    n[0] += 1\n    if n[0] == 20: raise RuntimeError('injected')\n    return orig(*a)\n"
                "watch.block_scores = boom\nwatch.main()\n")
        env = {**os.environ, "TEMP": str(self.tmp), "TMP": str(self.tmp), "TMPDIR": str(self.tmp)}
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("injected", r.stderr)
        self.assertEqual(list(self.tmp.glob("video-watch-*")), [])

    def test_error_during_analysis_removes_workdir(self):
        bad = self.tmp / "bad.mp4"
        bad.write_text("not a video")
        r = self.watch(bad, "--no-audio")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(list(self.tmp.glob("video-watch-*")), [])
        self.assertTrue(bad.exists())


if __name__ == "__main__":
    unittest.main()
