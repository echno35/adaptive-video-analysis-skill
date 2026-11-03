# video-watch (Claude Code skill)

Lets Claude "watch" a video you give it. Claude cannot play video, so the tool approximates it:

1. cuts the video into frames (one every 2 s) and tiles them into contact sheets (10 frames each)
2. transcribes the audio locally with `faster-whisper` (CPU, nothing uploaded for this step)
3. prints the sheet paths and the transcript so Claude can read them

Not affiliated with, endorsed by, or sponsored by Meta, Instagram or Anthropic.

## Default use: a local video file

```bash
python watch.py my-video.mp4
```

Typical sources: a screen recording you made, or a video you own or have permission to analyze.
This mode makes no requests to any video platform.

## Optional: downloading from a URL (explicit opt-in)

```bash
pip install -r requirements-download.txt     # yt-dlp, not installed by default
python watch.py --download "<url>"
```

This sends automated requests to the video's host. **Platform terms may prohibit that.** For Instagram, the
Terms of Use (section 4.2 in the Turkish page I read) and the Meta Automated Data Collection Terms restrict
automated access and data collection, and they do not appear to carve out public pages. This project does
not grant, obtain or imply any permission from Meta or Instagram, and it contains no login, cookie or
bypass features. If you use `--download`, you are responsible for whether that is allowed. Prefer a local
file when you can. Calling this "educational" does not change any of the above.

## What happens to your data

| Step | Where it runs | What is stored |
|---|---|---|
| Download (only with `--download`) | `yt-dlp` on your machine | `video.mp4` in a temp work dir |
| Frames | `ffmpeg` on your machine | `sheet_NN.png` in the temp work dir |
| Audio transcript | Whisper `small` on your machine (the model is downloaded once from Hugging Face) | `audio.wav` in the temp work dir; transcript is printed, and also written to `transcript.txt` only with `--keep` |
| Analysis | The script **prints the transcript to stdout and the sheet paths**; the skill then has Claude Code read the sheets | Both the transcript text and the sheet images become part of your Claude session, i.e. they are sent to Anthropic like any other message content |

Retention:

- By default the downloaded video, `audio.wav` and the transcript file are deleted when the run ends,
  including on errors. A local input file is never deleted.
- The contact sheets must outlive the run so Claude can open them. Delete them with
  `python watch.py --cleanup "<workdir>"` (the skill does this after reading). If you forget, work
  directories older than one hour are removed at the start of the next run.
- `--keep` disables all deletion.
- Cleanup removes local files only. **It does not delete anything already sent to a Claude session.**
  Check Anthropic's current privacy and retention settings for that.

Whether the sheets or transcript contain other people's faces, voices or usernames depends on the video.
Do not use this tool to identify people, and check the privacy law that applies to you.

## Install

```bash
git clone <this-repo-url> ~/.claude/skills/instagram
cd ~/.claude/skills/instagram
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
```

`SKILL.md` calls `.venv/Scripts/python` (Windows layout); on macOS/Linux change it to `.venv/bin/python`.
The first run downloads the Whisper `small` model (about 500 MB). Tests:
`python -m unittest discover -s tests` (they generate their own synthetic video, no third-party content).

## Licenses of dependencies (checked from installed package metadata)

| Package | License | Notes |
|---|---|---|
| `faster-whisper` | MIT | |
| `numpy` | BSD-3-Clause and others | |
| `imageio-ffmpeg` | BSD-2-Clause | The package itself. It downloads/bundles an ffmpeg binary. |
| ffmpeg binary used by `imageio-ffmpeg` | GPL v3 build | The binary I inspected reports `--enable-gpl --enable-version3`. This repo does **not** ship it; pip installs it on the user's machine. If you ever redistribute that binary you take on GPL obligations. |
| `yt-dlp` (optional) | Unlicense | PyPI package only; its standalone executables bundle GPLv3+ code. |
| Whisper `small` model weights | **not verified** | Loaded from Hugging Face by `faster-whisper`; I did not read the model card. Check it before redistributing anything. |

This repo has no license file yet. Pick one before publishing.

## Limits

- Claude sees sampled frames, not motion. Raise the frame rate with `--interval 1` for short clips.
- Music-only audio produces meaningless transcripts; check the printed language probability.
- No legal advice: this README is not one.
