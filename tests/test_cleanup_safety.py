"""Safety tests for work-directory removal (--cleanup, --keep-dir, error cleanup, stale sweep).

Everything is synthetic and runs in a private temp folder. No third-party content, no network.

Exit codes under test (documented in README.md and --help):
  0 removed and verified | 3 kept: not removed | 4 refused: could not verify it is safe | 5 removal incomplete | 1 other error
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import fixtures  # noqa: E402
import watch  # noqa: E402

WATCH = ROOT / "watch.py"
OLD = time.time() - watch.STALE_SECONDS - 600


def make_link(link: Path, target: Path) -> bool:
    """Directory symlink if the OS allows it, otherwise a Windows junction; False if neither works."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        return r.returncode == 0 and link.exists()
    return False


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="cleanup-safety-")).resolve()
        cls.video, _ = fixtures.silent(cls.base)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=self.base)).resolve()       # this test's TEMP
        self.user = self.tmp / "userfiles"
        self.user.mkdir()
        self.outside = self.tmp / "outside"
        self.outside.mkdir()

    # ---- helpers ----
    def env(self):
        return {**os.environ, "TEMP": str(self.tmp), "TMP": str(self.tmp), "TMPDIR": str(self.tmp), "HF_HUB_DISABLE_SYMLINKS_WARNING": "1"}

    def watch(self, *args):
        return subprocess.run([sys.executable, str(WATCH), *map(str, args)], capture_output=True, text=True, env=self.env())

    def make_workdir(self, name="video-watch-t1", parent=None, kind="local", manifest="ok", marker="ok",
                     keep=False, extra=(), source_inside=False, download_path=None, marker_kind=None):
        d = (parent or self.tmp) / name
        d.mkdir()
        if kind == "local":
            src = d / "sheet_99.png" if source_inside else self.user / "clip.mp4"
            src.write_bytes(b"USER-DATA")
        else:
            src = Path(download_path) if download_path else d / "video.mp4"
            if src.parent == d:
                src.write_bytes(b"downloaded")
        (d / "sheet_01.png").write_bytes(b"png")
        (d / "transcript.json").write_text("{}", encoding="utf-8")
        if marker == "ok":
            (d / ".video-watch").write_text(json.dumps({"tool": "video-watch", "version": "0.2", "mode": marker_kind or kind,
                                                        "source_path": str(src), "created": time.time()}), encoding="utf-8")
        elif marker == "corrupt":
            (d / ".video-watch").write_text("{not json", encoding="utf-8")
        if manifest == "ok":
            (d / "manifest.json").write_text(json.dumps({"version": "0.2", "source": {"kind": kind, "path": str(src)}}), encoding="utf-8")
        elif manifest == "corrupt":
            (d / "manifest.json").write_text("{oops", encoding="utf-8")
        elif manifest == "badshape":
            (d / "manifest.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
        if keep:
            (d / ".keep").write_text("kept", encoding="utf-8")
        for e in extra:
            (d / e).write_bytes(b"x")
        return d, src

    def sha(self, p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    def run_main(self, argv):
        """watch.main() in-process (so internals can be patched). Returns (exit code, stdout, stderr)."""
        old_argv, old_tmp = sys.argv, tempfile.tempdir
        tempfile.tempdir = str(self.tmp)
        out, err = io.TextIOWrapper(io.BytesIO(), encoding="utf-8"), io.StringIO()
        code = 0
        try:
            sys.argv = ["watch.py", *map(str, argv)]
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    watch.main()
                except SystemExit as e:
                    code = e.code if isinstance(e.code, int) else 1
                    if isinstance(e.code, str):
                        err.write(e.code)
        finally:
            sys.argv, tempfile.tempdir = old_argv, old_tmp
        out.flush()
        return code, out.buffer.getvalue().decode("utf-8"), err.getvalue()


class CleanupCommandTests(Base):
    def test_removed_is_verified(self):
        d, src = self.make_workdir()
        r = self.watch("--cleanup", d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("removed", r.stdout)
        self.assertFalse(d.exists())
        self.assertEqual(src.read_bytes(), b"USER-DATA")

    def test_resolved_path_forms(self):
        d, _ = self.make_workdir()
        self.assertEqual(self.watch("--cleanup", self.tmp / "outside" / ".." / d.name).returncode, 0)
        self.assertFalse(d.exists())

    def test_path_that_resolves_to_a_foreign_dir_is_refused(self):
        d, _ = self.make_workdir()
        foreign = self.tmp / "foreign"
        foreign.mkdir()
        (foreign / "keep.txt").write_text("mine")
        r = self.watch("--cleanup", d / ".." / "foreign")
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertTrue((foreign / "keep.txt").exists() and d.exists())

    def test_kept_dir_is_not_removed_and_says_so(self):
        d, _ = self.make_workdir(keep=True)
        r = self.watch("--cleanup", d)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertTrue(d.exists())
        self.assertIn("--force", r.stderr)
        self.assertNotIn("removed ", r.stdout)

    def test_force_removes_only_the_keep_protection(self):
        d, src = self.make_workdir(keep=True)
        r = self.watch("--cleanup", d, "--force")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(d.exists())
        self.assertTrue(src.exists())

    def test_force_without_cleanup_is_an_error(self):
        r = self.watch("--force", self.video)
        self.assertEqual(r.returncode, 1)

    def test_nothing_bypasses_the_safety_checks_even_with_force(self):
        other_parent = self.tmp / "elsewhere"
        other_parent.mkdir()
        cases = {
            "foreign name": lambda: self.make_workdir(name="not-ours"),
            "right name, wrong parent folder": lambda: self.make_workdir(parent=other_parent),
            "corrupt manifest": lambda: self.make_workdir(manifest="corrupt"),
            "manifest of the wrong shape": lambda: self.make_workdir(manifest="badshape"),
            "no manifest and no marker": lambda: self.make_workdir(manifest="missing", marker="missing"),
            "corrupt marker": lambda: self.make_workdir(manifest="missing", marker="corrupt"),
            "unexpected file": lambda: self.make_workdir(extra=["notes.txt"]),
            "video file in a local-source dir": lambda: self.make_workdir(extra=["video.mp4"]),
            "local source inside (manifest)": lambda: self.make_workdir(source_inside=True),
            "local source inside (marker only)": lambda: self.make_workdir(source_inside=True, manifest="missing"),
            "manifest and marker disagree": lambda: self.make_workdir(marker_kind="download"),
            "download path is not the work dir's video": lambda: self.make_workdir(kind="download", download_path=self.user / "other.mp4"),
        }
        for label, make in cases.items():
            for force in (False, True):
                with self.subTest(label, force=force):
                    d, src = make()
                    before = sorted(p.name for p in d.iterdir())
                    r = self.watch("--cleanup", d, *(["--force"] if force else []))
                    self.assertEqual(r.returncode, 4, f"{label}: {r.stdout} {r.stderr}")
                    self.assertEqual(sorted(p.name for p in d.iterdir()), before, "refused means untouched")
                    if src.exists():
                        self.assertEqual(src.read_bytes() in (b"USER-DATA", b"downloaded"), True)
                    shutil.rmtree(d)
                    if src.exists() and not str(src).startswith(str(d)):
                        src.unlink()

    def test_refusal_names_the_reason_and_does_not_dump_file_names(self):
        d, _ = self.make_workdir(extra=["notes.txt"] + [f"stray_{i}.txt" for i in range(40)])
        r = self.watch("--cleanup", d)
        self.assertEqual(r.returncode, 4)
        self.assertIn("unexpected", r.stderr)
        self.assertLess(len(r.stderr.splitlines()), 6)
        self.assertLess(r.stderr.count("stray_"), 2)

    def test_download_dir_with_ytdlp_leftovers_is_removable(self):
        d, _ = self.make_workdir(kind="download", extra=["video.f137.mp4", "video.mp4.part", "video.mp4.ytdl"])
        self.assertEqual(self.watch("--cleanup", d).returncode, 0)
        self.assertFalse(d.exists())

    def test_crash_residue_with_marker_but_no_manifest_is_removable(self):
        d, src = self.make_workdir(manifest="missing")
        self.assertEqual(self.watch("--cleanup", d).returncode, 0)
        self.assertFalse(d.exists())
        self.assertTrue(src.exists())

    def test_links_are_never_followed(self):
        real, src = self.make_workdir(name="video-watch-real", parent=self.outside)
        link = self.tmp / "video-watch-link"
        if not make_link(link, real):
            self.skipTest("cannot create a directory symlink or junction here")
        r = self.watch("--cleanup", link)
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertTrue((real / "manifest.json").exists() and (real / "sheet_01.png").exists())
        os.rmdir(link)

    def test_link_inside_a_work_dir_is_refused(self):
        d, _ = self.make_workdir()
        target = self.outside / "precious"
        target.mkdir()
        (target / "data.txt").write_text("precious")
        if not make_link(d / "detail_tmp_01", target):
            self.skipTest("cannot create a directory symlink or junction here")
        for force in (False, True):
            r = self.watch("--cleanup", d, *(["--force"] if force else []))
            self.assertEqual(r.returncode, 4, r.stderr)
            self.assertEqual((target / "data.txt").read_text(), "precious")
            self.assertTrue(d.exists())
        os.rmdir(d / "detail_tmp_01")


class KeepDirTests(Base):
    def test_marks_a_verified_dir_and_is_idempotent(self):
        d, _ = self.make_workdir()
        r = self.watch("--keep-dir", d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((d / ".keep").exists())
        self.assertIn("marked kept", r.stdout)
        self.assertEqual(self.watch("--keep-dir", d).returncode, 0)
        self.assertEqual(self.watch("--cleanup", d).returncode, 3)
        self.assertEqual(self.watch("--cleanup", d, "--force").returncode, 0)

    def test_refuses_unverifiable_dirs_and_changes_nothing(self):
        for label, make in {"foreign": lambda: self.make_workdir(name="not-ours"),
                            "corrupt manifest": lambda: self.make_workdir(manifest="corrupt"),
                            "local source inside": lambda: self.make_workdir(source_inside=True),
                            "unexpected file": lambda: self.make_workdir(extra=["notes.txt"])}.items():
            with self.subTest(label):
                d, _ = make()
                r = self.watch("--keep-dir", d)
                self.assertEqual(r.returncode, 4, r.stderr)
                self.assertFalse((d / ".keep").exists())
                shutil.rmtree(d)

    def test_marked_dir_survives_the_stale_sweep(self):
        d, _ = self.make_workdir()
        self.assertEqual(self.watch("--keep-dir", d).returncode, 0)
        os.utime(d, (OLD, OLD))
        self.assertEqual(self.watch(self.video, "--no-audio").returncode, 0)
        self.assertTrue(d.exists())


class SweepTests(Base):
    def run_analysis(self):
        r = self.watch(self.video, "--no-audio")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_sweep_removes_only_verified_stale_dirs(self):
        stale, _ = self.make_workdir(name="video-watch-stale")
        fresh, _ = self.make_workdir(name="video-watch-fresh")
        kept, _ = self.make_workdir(name="video-watch-kept", keep=True)
        unverifiable, _ = self.make_workdir(name="video-watch-unver", manifest="missing", marker="missing")
        stray, _ = self.make_workdir(name="video-watch-stray", extra=["notes.txt"])
        inside, src_inside = self.make_workdir(name="video-watch-inside", source_inside=True)
        for d in (stale, kept, unverifiable, stray, inside):
            os.utime(d, (OLD, OLD))
        r = self.run_analysis()
        self.assertFalse(stale.exists(), "stale + verified is removed")
        for d in (fresh, kept, unverifiable, stray, inside):
            self.assertTrue(d.exists(), f"{d.name} must survive")
        self.assertEqual(src_inside.read_bytes(), b"USER-DATA")
        self.assertIn("left in place", r.stderr)
        self.assertLess(len(r.stderr.splitlines()), 4)

    def test_sweep_never_follows_a_link(self):
        real, _ = self.make_workdir(name="video-watch-real", parent=self.outside)
        os.utime(real, (OLD, OLD))
        link = self.tmp / "video-watch-link"
        if not make_link(link, real):
            self.skipTest("cannot create a directory symlink or junction here")
        self.run_analysis()
        self.assertTrue((real / "manifest.json").exists() and (real / "sheet_01.png").exists())
        os.rmdir(link)

    def test_sweep_failure_is_reported_and_does_not_break_the_analysis(self):
        stale, _ = self.make_workdir(name="video-watch-stale")
        os.utime(stale, (OLD, OLD))
        with mock.patch.object(watch, "_unlink", side_effect=OSError("simulated")):
            code, out, err = self.run_main([self.video, "--no-audio"])
        self.assertEqual(code, 0, err)
        self.assertTrue(stale.exists())
        self.assertIn(str(stale), err)


class RemovalFailureTests(Base):
    """Platform-independent simulations of a removal that fails or only pretends to work."""

    def test_failing_unlink_gives_exit_5_with_the_path(self):
        d, _ = self.make_workdir(extra=[])
        for i in range(30):
            (d / f"sheet_{i + 10:02d}.png").write_bytes(b"x")
        with mock.patch.object(watch, "_unlink", side_effect=PermissionError("simulated lock")):
            code, out, err = self.run_main(["--cleanup", d])
        self.assertEqual(code, 5, err)
        self.assertIn(str(d), err)
        self.assertIn("incomplete", err)
        self.assertLess(len(err.splitlines()), 4)
        self.assertNotIn("sheet_20", err)
        self.assertTrue(d.exists())

    def test_removal_that_silently_does_nothing_is_not_reported_as_removed(self):
        d, _ = self.make_workdir()
        with mock.patch.object(watch, "_unlink", return_value=None), mock.patch.object(watch, "_rmdir", return_value=None):
            code, out, err = self.run_main(["--cleanup", d])
        self.assertEqual(code, 5, err)
        self.assertNotIn("removed", out)
        self.assertIn("still exists", err)

    def test_partial_removal_reports_the_remaining_dir_and_stays_retryable(self):
        d, _ = self.make_workdir()
        real_unlink = os.unlink

        def flaky(p):
            if os.path.basename(p) == "sheet_01.png":
                raise PermissionError("simulated lock")
            real_unlink(p)
        with mock.patch.object(watch, "_unlink", side_effect=flaky):
            code, out, err = self.run_main(["--cleanup", d])
        self.assertEqual(code, 5, err)
        self.assertIn(str(d), err)
        self.assertTrue((d / "sheet_01.png").exists())
        # the marker and manifest are removed last, only when everything else is gone, so the dir is still verifiable
        self.assertTrue((d / ".video-watch").exists() and (d / "manifest.json").exists())
        self.assertEqual(self.watch("--cleanup", d).returncode, 0)
        self.assertFalse(d.exists())

    @unittest.skipUnless(os.name == "nt", "a real file lock is only reproducible this way on Windows")
    def test_windows_file_lock_gives_exit_5_then_works_after_release(self):
        d, _ = self.make_workdir()
        with open(d / "sheet_01.png", "rb"):
            r = self.watch("--cleanup", d)
            self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
            self.assertIn(str(d), r.stderr)
            self.assertTrue(d.exists())
        self.assertEqual(self.watch("--cleanup", d).returncode, 0)
        self.assertFalse(d.exists())


class ErrorPathTests(Base):
    def find_workdirs(self):
        return sorted(p for p in self.tmp.glob("video-watch-*") if p.is_dir())

    def test_failure_mid_analysis_removes_the_work_dir(self):
        with mock.patch.object(watch, "scan", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.run_main([self.video, "--no-audio"])
        self.assertEqual(self.find_workdirs(), [])

    def test_failure_with_failing_removal_reports_the_dir_and_keeps_the_original_error(self):
        with mock.patch.object(watch, "scan", side_effect=RuntimeError("injected")), \
                mock.patch.object(watch, "_unlink", side_effect=OSError("simulated")):
            old = tempfile.tempdir
            tempfile.tempdir = str(self.tmp)
            sys.argv, saved = ["watch.py", str(self.video), "--no-audio"], sys.argv
            err = io.StringIO()
            try:
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.TextIOWrapper(io.BytesIO(), encoding="utf-8")):
                    with self.assertRaises(RuntimeError) as cm:
                        watch.main()
            finally:
                tempfile.tempdir, sys.argv = old, saved
        self.assertEqual(str(cm.exception), "injected")
        left = self.find_workdirs()
        self.assertEqual(len(left), 1)
        self.assertIn(str(left[0]), err.getvalue())
        self.assertIn("left in place", err.getvalue())

    def test_error_cleanup_refuses_when_an_unexpected_file_appeared(self):
        def scan_then_fail(video, w, h, out):
            (out / "notes.txt").write_text("not ours")
            raise RuntimeError("injected")
        with mock.patch.object(watch, "scan", side_effect=scan_then_fail):
            with self.assertRaises(RuntimeError):
                self.run_main([self.video, "--no-audio"])
        left = self.find_workdirs()
        self.assertEqual(len(left), 1)
        self.assertTrue((left[0] / "notes.txt").exists())

    def test_error_with_keep_leaves_the_dir_and_says_where(self):
        with mock.patch.object(watch, "scan", side_effect=RuntimeError("injected")):
            old = tempfile.tempdir
            tempfile.tempdir = str(self.tmp)
            saved = sys.argv
            sys.argv = ["watch.py", str(self.video), "--no-audio", "--keep"]
            err = io.StringIO()
            try:
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.TextIOWrapper(io.BytesIO(), encoding="utf-8")):
                    with self.assertRaises(RuntimeError):
                        watch.main()
            finally:
                tempfile.tempdir, sys.argv = old, saved
        left = self.find_workdirs()
        self.assertEqual(len(left), 1)
        self.assertIn("kept (--keep)", err.getvalue())
        self.assertIn(str(left[0]), err.getvalue())
        self.assertTrue((left[0] / ".keep").exists())

    def test_every_analysis_writes_an_ownership_marker_first(self):
        r = self.watch(self.video, "--no-audio", "--keep")
        self.assertEqual(r.returncode, 0, r.stderr)
        (d,) = self.find_workdirs()
        m = json.loads((d / ".video-watch").read_text(encoding="utf-8"))
        self.assertEqual((m["tool"], m["mode"]), ("video-watch", "local"))
        self.assertEqual(Path(m["source_path"]).resolve(), self.video.resolve())


class EndToEndTests(Base):
    def test_local_source_is_untouched_by_every_command(self):
        before = self.sha(self.video)
        r = self.watch(self.video, "--no-audio")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = Path(next(l[9:] for l in r.stdout.splitlines() if l.startswith("workdir: ")))
        self.assertEqual(self.watch("--keep-dir", d).returncode, 0)
        self.assertEqual(self.watch("--cleanup", d).returncode, 3)
        self.assertEqual(self.watch("--cleanup", d, "--force").returncode, 0)
        self.assertFalse(d.exists())
        self.assertEqual(self.sha(self.video), before)

    def test_keep_run_prints_how_to_remove_it_and_default_run_does_not(self):
        k = self.watch(self.video, "--no-audio", "--keep")
        self.assertIn("--force", k.stdout.splitlines()[-1])
        n = self.watch(self.video, "--no-audio")
        self.assertNotIn("--force", n.stdout)
        self.assertIn("--cleanup", n.stdout.splitlines()[-1])

    def test_exit_codes_are_documented_in_help(self):
        h = self.watch("--help").stdout
        for needle in ("exit codes", "kept", "refused", "incomplete", "--keep-dir", "--force"):
            self.assertIn(needle, h)


if __name__ == "__main__":
    unittest.main()
