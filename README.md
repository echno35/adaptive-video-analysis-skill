# video-watch (Claude Code skill)

Lets Claude "watch" a video you give it. Claude cannot play video, so the tool prepares evidence locally and
Claude reads it:

1. **Scan** (local, nothing sent): about 5 real frames per second are compared block by block; a frame whose
   largest per-block colour change exceeds a threshold becomes a *candidate*. If nothing changes for 10 s a
   "heartbeat" candidate is added.
2. **Overview** (sent when Claude opens it): at most 24 candidates, chosen to differ from each other, on
   labelled sheets (12 small tiles each, tile long edge ≤ 400 px, sheet long edge ≤ 1568 px). Every candidate
   that did not fit is listed as a "not shown" interval, so nothing detected is dropped silently.
3. **Detail on request**: `--detail` extracts full-resolution frames or crops from one time range, within a budget.
4. **Transcript**: local `faster-whisper` with voice-activity filtering; confident segments are printed,
   low-confidence ones are listed by time and can be printed with `--transcript`.

Not affiliated with, endorsed by, or sponsored by Meta, Instagram or Anthropic.

## Default use: a local video file

```bash
python watch.py my-video.mp4
python watch.py --detail "<workdir>" --range 12-14 --fps 2            # more frames from 12-14 s
python watch.py --detail "<workdir>" --range 12-12 --crop 0.7,0,0.3,0.2   # one crop (fractions x,y,w,h)
python watch.py --transcript "<workdir>" --all --range 10-20         # include low-confidence segments
python watch.py --cleanup "<workdir>"
```

Typical sources: a screen recording you made, or a video you own or have permission to analyze.

**Network behavior, precisely.** Local-file mode never connects to Instagram or any video platform. It is not
"fully offline" in every case:

| Situation | Network requests |
|---|---|
| `pip install` of the dependencies | yes (PyPI; the ffmpeg binary ships inside the `imageio-ffmpeg` wheel) |
| First transcription, Whisper model not cached yet | yes: downloads `Systran/faster-whisper-small` (about 500 MB) from `huggingface.co` |
| Later runs, model cached | none observed (0 connections in my test with v0.1's loader, which v0.2 keeps) |
| `--no-audio` | none (the model is never loaded) |

Set `HF_HUB_OFFLINE=1` to forbid Hugging Face requests entirely. Images and transcript text still go to Claude
when it reads them, which is a transfer by Claude Code, not by this script.

## Optional: downloading from a URL (explicit opt-in)

```bash
pip install -r requirements-download.txt     # yt-dlp, not installed by default
python watch.py --download "<url>"                     # video deleted at the end of the run
python watch.py --download "<url>" --retain-source     # video kept until --cleanup, enables --detail
```

This sends automated requests to the video's host. **Platform terms may prohibit that.** For Instagram, the
Terms of Use (section 4.2 in the Turkish page I read) and the Meta Automated Data Collection Terms restrict
automated access and data collection, and they do not appear to carve out public pages. This project does
not grant, obtain or imply any permission from Meta or Instagram, and it contains no login, cookie or
bypass features. If you use `--download`, you are responsible for whether that is allowed. Prefer a local
file when you can. Calling this "educational" does not change any of the above.

## What happens to your data

| Item | Where | Kept until |
|---|---|---|
| Your local input file | where it is | never copied, never deleted; its path, size and mtime are recorded so `--detail` can refuse a changed file |
| Downloaded video (`--download`) | temp work dir | deleted at the end of the run; with `--retain-source` kept until `--cleanup` |
| `audio.wav` | temp work dir | deleted at the end of the run |
| Overview sheets, detail images | temp work dir | `--cleanup` |
| `transcript.json` (all segments, incl. low-confidence text) | temp work dir | `--cleanup` |
| `manifest.json` (candidate times, scores, budget) | temp work dir | `--cleanup` |

- **On errors** during an analysis the whole work dir is deleted. A failed `--detail` removes its partial images
  and leaves the manifest and budget unchanged.
- **Stale sweep**: at the start of each new analysis (not on `--detail`, `--transcript` or `--cleanup`), work
  dirs older than one hour are deleted, including any retained download. There is no background process, so
  nothing is deleted "after an hour" unless you run another analysis.
- **`--keep`** disables all deletion (video and audio stay) and exempts the work dir from the stale sweep; only
  `--cleanup` removes it.
- **`--cleanup`** only deletes directories this tool created in the system temp folder.
- Cleanup removes local files only. **It does not delete anything already sent to a Claude session.**
  Check Anthropic's current privacy and retention settings for that.

Whether frames or transcript contain other people's faces, voices or usernames depends on the video. Do not
use this tool to identify people, and check the privacy law that applies to you. Text and speech in a video
are treated by the skill as data, not instructions.

## Image size and tokens

The tool reports the **number of images it produced for reading, their real pixel sizes and the total pixels**.
It does not know which images Claude actually opened, and it does not report tokens, because the cost depends
on the model: Anthropic's vision documentation
([platform.claude.com/docs/en/build-with-claude/vision](https://platform.claude.com/docs/en/build-with-claude/vision),
read 2026-11-04) describes a per-model maximum resolution, a 1568 px long edge for some models and a higher one
for newer models, with larger images downscaled, and counts visual tokens per 28×28 px patch. I could not read the
full per-model table, so no model-specific estimate is given here. The 1568 px sheet edge and 400 px tile edge in
this tool are **our own budget**, not a server limit.

## Install

```bash
git clone https://github.com/echno35/instagram-video-analyzer-skill.git ~/.claude/skills/instagram
cd ~/.claude/skills/instagram
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
```

`SKILL.md` calls `.venv/Scripts/python` (Windows layout); on macOS/Linux change it to `.venv/bin/python`.

Tests: `python -m unittest discover -s tests`. They generate their own synthetic videos (no third-party content)
and check local behaviour only, not answer quality. `python bench/compare.py watch.py` measures what a version
produces on the same synthetic videos (see below).

## Local measurements: v0.1 vs v0.2 on synthetic videos

What this is: both versions run with `--no-audio` on **16 synthetic videos** generated by `tests/fixtures.py`
(8 kinds; four kinds have 3 variants each with the event at a different time). Raw numbers:
`bench/baseline-v0.1.json` (v0.1 = commit `cab7e87`) and `bench/results-v0.2.json`. Everything below is measured
locally. **It is not a measurement of tokens, of what Claude actually reads, or of answer quality**, and the
videos are synthetic, so it says nothing yet about real videos.

"Event in images" means the event's unique colour is present in the produced images (checked from pixels).

| Kind (videos) | MP per video v0.1 → v0.2 | Images per video v0.1 → v0.2 | Events in images v0.1 → v0.2 | Printed chars per video v0.1 → v0.2 |
|---|---|---|---|---|
| static screen, 30 s, vertical (1) | 4.61 → 0.27 | 2 → 1 | no event | 509 → 1135 |
| small change, 40×20 px for 3 s (1) | 1.46 → 0.36 | 2 → 1 | 1/1 → 1/1 | 509 → 1255 |
| 0.3 s flash at 2 / 14 / 27 s (3) | 1.46 → 0.55 | 2 → 1 | 0/3 → 3/3 | 509 → ~1146 |
| noise + 0.3 s mark at 3 / 14 / 26 s (3) | 1.46 → 2.19 | 2 → 2 | 0/3 → 3/3 | 509 → ~2240 |
| scrolling + 0.3 s mark at 4 / 20 / 28 s (3) | 1.46 → 2.19 | 2 → 2 | 0/3 → 3/3 | 509 → ~2243 |
| 180 s, 60 stronger changes + 0.3 s mark at 5 / 95 / 170 s (3) | 6.58 → 2.19 | 9 → 2 | 0/3 → 3/3 | 1265 → ~2391 |
| test pattern with changing counter (1) | 0.73 → 2.19 | 1 → 2 | no event | 401 → 2254 |
| silent video (1) | 0.73 → 0.09 | 1 → 1 | no event | 401 → 1121 |
| **Total over the 16 videos** | **40.42 → 24.30 MP** | **51 → 26** | **1/13 → 13/13** | **10196 → 29826** |

Totals are sums over all 16 videos, so each 3-variant row counts three times. Other measured facts:

- v0.2 produces **more** pixels than v0.1 on the busy videos (noise, scrolling, changing counter) and prints
  **2-5x more text** on every video (tile times, not-shown intervals, budget lines). Printed text is also read by Claude.
- Local runtime for the 16 videos: 5.5 s → 43.1 s (CPU, this machine).
- With audio (`bench/baseline-v0.1-audio.json`, `bench/results-v0.2-audio.json`, 2 videos): v0.1 crashes on the
  silent video, v0.2 reports "no audio track".
- 13/13 events in the images is a result on these videos, not a guarantee: with more candidates than the cap, the
  promise is only "shown or listed as not shown".

## Compatibility changes in v0.2

- `--interval` was removed. Frames are chosen by change detection; for denser frames use
  `--detail WORKDIR --range A-B --fps F`. Passing `--interval` now fails with an explanation.
- The printed output format changed (`VISUAL` / `SPOKEN` sections, `not shown:` intervals, budget lines).
  Anything parsing v0.1 output needs updating; `workdir:` and `sheet:` lines still start the same way.
- Sheets hold up to 12 small labelled tiles instead of 10 tiles of 360 px width.
- The transcript is stored as `transcript.json` in the work dir until `--cleanup` (v0.1 wrote `transcript.txt`
  only with `--keep`). Low-confidence segments are listed by time instead of printed.
- `--keep` work dirs are now exempt from the stale sweep (v0.1 could delete them on a later run).
- Unchanged: local file is the default, download is opt-in, a downloaded video is deleted at the end of the run
  unless `--retain-source` or `--keep`.

## Tested on

- **Tested:** Windows 11 Pro only, Python 3.12.10, CPU only. Local-file mode and `--download` (against a local
  HTTP server serving a self-generated video) pass the test suite there.
- **Not tested:** macOS, Linux, other Python versions, GPU/CUDA, other Whisper model sizes, and
  **downloading from Instagram with the current version of this code**. Instagram changes often and may
  block or alter what `yt-dlp` can do; no result from an earlier version carries over.
  The code is plain Python and should be portable, but that is an expectation, not a result.
  Overview labels need a TrueType font at a known path; without one the times are only printed.

## License

The code in this repository is licensed under the MIT License (see [LICENSE](LICENSE)). Third-party
dependencies, model weights and binaries are **not** covered by it and remain under their own licenses, listed
below. Installing or redistributing them means complying with those licenses.

| Component | License | Notes |
|---|---|---|
| `faster-whisper` | MIT | from package metadata |
| `numpy` | BSD-3-Clause and others | from package metadata |
| `imageio-ffmpeg` | BSD-2-Clause | the Python package; its wheel contains an ffmpeg binary |
| ffmpeg binary inside `imageio-ffmpeg` | GPL v3 build | the binary I inspected reports `--enable-gpl --enable-version3`. This repo does not ship it; pip installs it on your machine. Redistributing that binary brings GPL obligations. |
| `yt-dlp` (optional) | Unlicense | PyPI package only; its standalone executables bundle GPLv3+ code |
| Whisper model weights `Systran/faster-whisper-small` | see note below | The model actually downloaded (confirmed in the `faster_whisper` source and the local cache, revision `536b0662742c02347bc0e980a01041f333bce120`). |

Whisper model license, as stated by each source (read 2026-11-04):

- OpenAI's official repository ([github.com/openai/whisper](https://github.com/openai/whisper), README and
  `LICENSE`) says Whisper's code and model weights are released under the MIT License (`Copyright (c) 2022 OpenAI`).
- The Hugging Face card of the downloaded conversion
  ([Systran/faster-whisper-small](https://huggingface.co/Systran/faster-whisper-small)) is tagged `license: mit`
  and says it is a CTranslate2 conversion of `openai/whisper-small`.
- The Hugging Face card of the original checkpoint
  ([openai/whisper-small](https://huggingface.co/openai/whisper-small)) is tagged `apache-2.0`.

The sources do not all use the same label, and I could not determine from them why. I do not treat this as an
established license conflict. Two of the three sources say MIT. This is not a legal conclusion. If you
redistribute the weights, check the sources yourself and include the notices they require.

## Limits

- Claude sees selected frames, not motion. Changes shorter than about 0.25 s can fall between scanned frames.
- With more candidates than the overview cap, a detected change may be listed as "not shown" instead of being
  on a sheet; only "shown or listed" is guaranteed, not "shown".
- The change threshold is fixed. Very low-contrast changes can stay below it; noise and scrolling make almost
  every scanned frame a candidate.
- Selection was tested on synthetic videos up to 3 minutes. Memory grows with the number of candidates.
- Machine transcription can be wrong; voice-activity filtering can miss quiet speech.
- No legal advice: this README is not one.
