"""Synthetic test videos with known ground truth. Everything is generated here; no third-party content.

Each fixture returns (path, events). An event is a time window in which a uniquely coloured mark is
visible, so its presence in any produced image can be checked from pixels alone.
"""
import struct
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np

FF = imageio_ffmpeg.get_ffmpeg_exe()
RED = "red"
GREEN = "green"


def _ff(args):
    subprocess.run([FF, "-y", "-loglevel", "error", *args], check=True)


def _box(x, y, w, h, color, t0, t1):
    hexcol = {"red": "0xFF0000", "green": "0x00FF00"}[color]
    return f"drawbox=x={x}:y={y}:w={w}:h={h}:color={hexcol}:t=fill:enable='between(t,{t0},{t1})'"


def _video(path, src, vf=None, tone=None):
    args = ["-f", "lavfi", "-i", src]
    if tone:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={tone}", "-shortest"]
    if vf:
        args += ["-vf", vf]
    _ff([*args, "-pix_fmt", "yuv420p", str(path)])
    return path


def static(d: Path):
    return _video(d / "static.mp4", "color=c=white:s=1080x1920:r=30:d=30", tone=30), []


def small_change(d: Path):
    ev = {"t0": 7.0, "t1": 10.0, "color": GREEN}
    vf = _box(1200, 20, 40, 20, GREEN, ev["t0"], ev["t1"])
    return _video(d / "small_change.mp4", "color=c=0x808080:s=1280x720:r=30:d=30", vf), [ev]


def flash(d: Path, at: float):
    ev = {"t0": at, "t1": at + 0.3, "color": RED}
    vf = _box(0, 0, "iw", "ih", RED, ev["t0"], ev["t1"])
    return _video(d / f"flash_{at:05.2f}.mp4", "color=c=white:s=640x360:r=30:d=30", vf), [ev]


def noise_event(d: Path, at: float = 14.05):
    ev = {"t0": at, "t1": at + 0.3, "color": RED}
    vf = "noise=c0s=40:c0f=t," + _box(260, 120, 120, 120, RED, ev["t0"], ev["t1"])
    return _video(d / f"noise_{at:06.2f}.mp4", "color=c=0x808080:s=640x360:r=30:d=30", vf), [ev]


def scroll_event(d: Path, at: float = 20.05):
    # grey stripes moving 40 px/s: every scanned frame changes strongly, the event is one short mark among them
    ev = {"t0": at, "t1": at + 0.3, "color": RED}
    src = "nullsrc=s=640x360:r=15:d=30,geq=lum='128+100*sin((X+40*T)/12)':cb=128:cr=128"
    vf = "format=yuv420p," + _box(260, 120, 120, 120, RED, ev["t0"], ev["t1"])
    return _video(d / f"scroll_{at:06.2f}.mp4", src, vf), [ev]


def long_event(d: Path, at: float = 95.05):
    # 180 s, full-frame black/white toggle every 3 s (60 strong changes, all scoring higher than the event)
    ev = {"t0": at, "t1": at + 0.3, "color": RED}
    vf = ("drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='lt(mod(t,6),3)',"
          + _box(260, 120, 120, 120, RED, ev["t0"], ev["t1"]))
    return _video(d / f"long_{at:06.2f}.mp4", "color=c=white:s=640x360:r=10:d=180", vf), [ev]


def small_text(d: Path):
    # testsrc draws a frame counter; used for detail/crop geometry, not for readability claims
    return _video(d / "small_text.mp4", "testsrc=s=1920x1080:r=10:d=10"), []


def silent(d: Path):
    return _video(d / "silent.mp4", "color=c=white:s=640x360:r=10:d=6"), []


ALL = {
    "static": static,
    "small_change": small_change,
    "flash_02": lambda d: flash(d, 2.05),
    "flash_14": lambda d: flash(d, 14.05),
    "flash_27": lambda d: flash(d, 27.05),
    "noise_03": lambda d: noise_event(d, 3.05),
    "noise_14": lambda d: noise_event(d, 14.05),
    "noise_26": lambda d: noise_event(d, 26.05),
    "scroll_04": lambda d: scroll_event(d, 4.05),
    "scroll_20": lambda d: scroll_event(d, 20.05),
    "scroll_28": lambda d: scroll_event(d, 28.05),
    "long_005": lambda d: long_event(d, 5.05),
    "long_095": lambda d: long_event(d, 95.05),
    "long_170": lambda d: long_event(d, 170.05),
    "small_text": small_text,
    "silent": silent,
}


def png_size(path: Path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def color_pixels(path: Path, color: str) -> int:
    w, h = png_size(path)
    raw = subprocess.run([FF, "-loglevel", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    px = np.frombuffer(raw, np.uint8).reshape(h, w, 3).astype(int)
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    mask = (r > 180) & (g < 90) & (b < 90) if color == RED else (g > 180) & (r < 90) & (b < 90)
    return int(mask.sum())
