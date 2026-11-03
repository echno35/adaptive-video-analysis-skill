"""Turn a video into contact sheets (frames) plus a local Whisper transcript.

Usage:
  watch.py FILE                  analyze a local video file (default, no network access)
  watch.py --download URL        opt in to downloading a video from a URL with yt-dlp
  watch.py --cleanup DIR         remove a work directory printed by an earlier run

Default behaviour: the downloaded video, the extracted audio and the transcript file are
deleted when the run ends (also on errors). The contact sheets stay until the caller has read
them, then `--cleanup DIR` removes them; leftover work directories older than an hour are swept
at the start of the next run. `--keep` skips all deletion. A local input file is never touched.
"""
import argparse
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import imageio_ffmpeg

PREFIX = "video-watch-"
STALE_SECONDS = 3600
FF = imageio_ffmpeg.get_ffmpeg_exe()


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def is_work_dir(path: Path) -> bool:
    return path.is_dir() and path.name.startswith(PREFIX) and path.resolve().parent == Path(tempfile.gettempdir()).resolve()


def sweep_stale():
    now = time.time()
    for d in Path(tempfile.gettempdir()).glob(PREFIX + "*"):
        if is_work_dir(d) and now - d.stat().st_mtime > STALE_SECONDS:
            shutil.rmtree(d, ignore_errors=True)


def download(url: str, out: Path) -> Path:
    if importlib.util.find_spec("yt_dlp") is None:
        sys.exit("yt-dlp is not installed. Install the optional dependency: pip install -r requirements-download.txt")
    print(
        "NOTE: --download makes automated requests to the video's host. Platform terms (for example "
        "Instagram's) may prohibit this; nothing here grants permission. You are responsible for the use.",
        file=sys.stderr,
    )
    subprocess.run([
        sys.executable, "-m", "yt_dlp", "--ffmpeg-location", FF,
        "-f", "bv*+ba/b", "--merge-output-format", "mp4",
        "--no-playlist", "-o", str(out / "video.%(ext)s"), url,
    ], check=True, stdout=sys.stderr)
    return out / "video.mp4"


def transcribe(video: Path, out: Path) -> str:
    import numpy as np
    from faster_whisper import WhisperModel

    wav = out / "audio.wav"
    run([FF, "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    with wave.open(str(wav)) as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    # CPU explicitly: CUDA libraries are often missing; a numpy array avoids a PyAV API mismatch
    segs, info = WhisperModel("small", device="cpu", compute_type="int8").transcribe(audio)
    lines = [f"[{s.start:6.1f}s] {s.text.strip()}" for s in segs]
    return f"language: {info.language} (p={info.language_probability:.2f})\n" + ("\n".join(lines) or "(no speech detected)")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="local video file")
    ap.add_argument("--download", metavar="URL", help="download the video from URL with yt-dlp instead (opt-in)")
    ap.add_argument("--cleanup", metavar="DIR", help="delete a work directory created by this tool and exit")
    ap.add_argument("--keep", action="store_true", help="keep every file, including downloaded video, audio, transcript")
    ap.add_argument("--interval", type=float, default=2.0, help="seconds between frames (default 2)")
    ap.add_argument("--no-audio", action="store_true", help="skip audio transcription")
    a = ap.parse_args()

    if a.cleanup:
        d = Path(a.cleanup)
        if not is_work_dir(d):
            sys.exit(f"refusing to delete {d}: not a work directory created by this tool")
        shutil.rmtree(d)
        print(f"removed {d}")
        return
    if bool(a.file) == bool(a.download):
        ap.error("give either a local FILE or --download URL")

    sweep_stale()
    out = Path(tempfile.mkdtemp(prefix=PREFIX))
    try:
        video = download(a.download, out) if a.download else Path(a.file)
        if not video.is_file():
            sys.exit(f"video not found: {video}")

        run([FF, "-y", "-i", str(video), "-vf", f"fps=1/{a.interval},scale=360:-1,tile=5x2", str(out / "sheet_%02d.png")])
        transcript = "audio transcription skipped (--no-audio)" if a.no_audio else transcribe(video, out)
        if a.keep:
            (out / "transcript.txt").write_text(transcript, encoding="utf-8")

        print(f"workdir: {out}")
        for s in sorted(out.glob("sheet_*.png")):
            print(f"sheet: {s}")
        print("transcript:\n" + transcript)
        if not a.keep:
            for name in ("video.mp4", "audio.wav"):
                (out / name).unlink(missing_ok=True)
            print(f'when done reading the sheets run: watch.py --cleanup "{out}"')
    except BaseException:
        if not a.keep:
            shutil.rmtree(out, ignore_errors=True)
        raise


if __name__ == "__main__":
    main()
