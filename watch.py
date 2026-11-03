"""Download an Instagram reel/post video, build contact sheets and transcribe its audio.

Usage: watch.py <url> [--out DIR] [--interval SECONDS]
Prints the output paths; the caller then Reads the sheet images.
"""
import argparse, os, subprocess, sys, wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np

FF = imageio_ffmpeg.get_ffmpeg_exe()


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default=str(Path(os.environ.get("TEMP", ".")) / "instagram-watch"))
    ap.add_argument("--interval", type=float, default=2.0)
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    video = out / "video.mp4"

    subprocess.run([
        sys.executable, "-m", "yt_dlp", "--ffmpeg-location", FF,
        "-f", "bv*+ba/b", "--merge-output-format", "mp4",
        "--no-playlist", "-o", str(out / "video.%(ext)s"), "--force-overwrites", a.url,
    ], check=True)

    # contact sheets: 10 frames per sheet, 5x2 grid
    for old in out.glob("sheet_*.png"):
        old.unlink()
    run([FF, "-y", "-i", str(video), "-vf",
         f"fps=1/{a.interval},scale=360:-1,tile=5x2", str(out / "sheet_%02d.png")])

    wav = out / "audio.wav"
    run([FF, "-y", "-i", str(video), "-ac", "1", "-ar", "16000", str(wav)])

    from faster_whisper import WhisperModel
    w = wave.open(str(wav))
    audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    # CPU explicitly: CUDA libs are usually missing; numpy input avoids a PyAV API mismatch
    segs, info = WhisperModel("small", device="cpu", compute_type="int8").transcribe(audio)
    lines = [f"[{s.start:6.1f}s] {s.text.strip()}" for s in segs]
    (out / "transcript.txt").write_text("\n".join(lines), encoding="utf-8")

    print(f"video: {video}")
    for s in sorted(out.glob("sheet_*.png")):
        print(f"sheet: {s}")
    print(f"language: {info.language} (p={info.language_probability:.2f})")
    print("transcript:\n" + ("\n".join(lines) or "(no speech detected)"))


if __name__ == "__main__":
    main()
