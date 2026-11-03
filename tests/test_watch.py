"""Tests use a synthetic video generated here (test pattern + sine tone), no third-party content.

Run: python -m unittest discover -s tests
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent.parent
WATCH = ROOT / "watch.py"
FF = imageio_ffmpeg.get_ffmpeg_exe()


class WatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="watch-test-"))
        cls.video = cls.base / "sample.mp4"
        subprocess.run([
            FF, "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=5",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
            "-shortest", "-pix_fmt", "yuv420p", str(cls.video),
        ], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def setUp(self):
        # point tempfile at an empty dir so leftovers are visible
        self.tmp = Path(tempfile.mkdtemp(dir=self.base))

    def watch(self, *args):
        env = {**os.environ, "TEMP": str(self.tmp), "TMP": str(self.tmp), "TMPDIR": str(self.tmp)}
        return subprocess.run([sys.executable, str(WATCH), *args], capture_output=True, text=True, env=env)

    def workdirs(self):
        return list(self.tmp.glob("video-watch-*"))

    def test_local_file_default_cleanup(self):
        r = self.watch(str(self.video), "--no-audio", "--interval", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        (d,) = self.workdirs()
        self.assertTrue(list(d.glob("sheet_*.png")))
        self.assertFalse((d / "audio.wav").exists())
        self.assertFalse((d / "transcript.txt").exists())
        self.assertTrue(self.video.exists(), "local input must never be deleted")
        c = self.watch("--cleanup", str(d))
        self.assertEqual(c.returncode, 0, c.stderr)
        self.assertEqual(self.workdirs(), [])

    def test_keep_retains_audio_and_transcript(self):
        r = self.watch(str(self.video), "--keep")
        self.assertEqual(r.returncode, 0, r.stderr)
        (d,) = self.workdirs()
        self.assertTrue((d / "audio.wav").exists())
        self.assertTrue((d / "transcript.txt").exists())
        self.assertIn("transcript:", r.stdout)

    def test_transcript_is_printed_to_stdout(self):
        r = self.watch(str(self.video))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("language:", r.stdout)
        (d,) = self.workdirs()
        self.assertFalse((d / "audio.wav").exists())

    def test_failure_leaves_nothing_behind(self):
        bad = self.base / "bad.mp4"
        bad.write_text("not a video")
        r = self.watch(str(bad), "--no-audio")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.workdirs(), [])

    def test_missing_file_leaves_nothing_behind(self):
        r = self.watch(str(self.base / "nope.mp4"))
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.workdirs(), [])

    def test_cleanup_refuses_foreign_directory(self):
        victim = self.base / "keepme"
        victim.mkdir()
        r = self.watch("--cleanup", str(victim))
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(victim.exists())

    def test_download_is_opt_in(self):
        self.assertNotEqual(self.watch().returncode, 0)
        both = self.watch(str(self.video), "--download", "https://example.invalid/x")
        self.assertNotEqual(both.returncode, 0)
        self.assertEqual(self.workdirs(), [])


if __name__ == "__main__":
    unittest.main()
