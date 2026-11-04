"""Measure what a version of watch.py produces on the synthetic fixtures.

Usage: python bench/compare.py SCRIPT [SCRIPT ...] [--json OUT]

Everything reported is measured locally: exit code, number and size of the images produced for
reading, total pixels, stdout size, runtime, and whether each known event is visible in those images.
It does NOT measure tokens, what Claude actually reads, or answer quality.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
import fixtures  # noqa: E402


def measure(script: Path, video: Path, events, tmp: Path, args):
    env = {**os.environ, "TEMP": str(tmp), "TMP": str(tmp), "TMPDIR": str(tmp),
           "HF_HUB_DISABLE_SYMLINKS_WARNING": "1"}
    t = time.time()
    r = subprocess.run([sys.executable, str(script), str(video), *args], capture_output=True, text=True, env=env)
    runtime = round(time.time() - t, 1)
    dirs = list(tmp.glob("video-watch-*"))
    images = sorted(p for d in dirs for p in d.glob("*.png"))
    sizes = [fixtures.png_size(p) for p in images]
    row = {
        "rc": r.returncode,
        "images": len(images),
        "sizes": [f"{w}x{h}" for w, h in sizes],
        "total_pixels": sum(w * h for w, h in sizes),
        "stdout_chars": len(r.stdout),
        "runtime_s": runtime,
        "events_visible": [any(fixtures.color_pixels(p, e["color"]) >= 4 for p in images) for e in events],
    }
    manifest = next((d / "manifest.json" for d in dirs if (d / "manifest.json").exists()), None)
    if manifest:
        cands = json.loads(manifest.read_text(encoding="utf-8"))["candidates"]
        row["events_detected_in_scan"] = [any(e["t0"] <= c["t"] <= e["t1"] for c in cands) for e in events]
        row["candidates"] = len(cands)
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scripts", nargs="+", type=Path)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--audio", action="store_true", help="also transcribe (slower); default --no-audio")
    ap.add_argument("--only", nargs="+", choices=list(fixtures.ALL), help="limit to these fixtures")
    ap.add_argument("--labels", nargs="+", help="names for the scripts in the JSON (default: file name); "
                    "keeps local paths out of committed results")
    a = ap.parse_args()
    labels = a.labels or [s.name for s in a.scripts]
    if len(labels) != len(a.scripts):
        ap.error("--labels needs one name per script")

    base = Path(tempfile.mkdtemp(prefix="watch-bench-"))
    results = {}
    try:
        vids = {name: make(base) for name, make in fixtures.ALL.items() if not a.only or name in a.only}
        for script, label in zip(a.scripts, labels):
            res = {}
            for name, (video, events) in vids.items():
                tmp = Path(tempfile.mkdtemp(dir=base))
                res[name] = measure(script, video, events, tmp, [] if a.audio else ["--no-audio"])
                print(f"{label:>14} {name:<13} {json.dumps(res[name])}")
            results[label] = res
    finally:
        shutil.rmtree(base, ignore_errors=True)
    if a.json:
        a.json.write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
