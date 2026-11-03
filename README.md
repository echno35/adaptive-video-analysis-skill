# video-watch (Claude Code skill)

Lets Claude "watch" a video you give it. Claude cannot play video, so the tool approximates it:

1. cuts the video into frames (one every 2 s) and tiles them into contact sheets (10 frames each)
2. transcribes the audio locally with `faster-whisper` (CPU, the audio is not uploaded for this step)
3. prints the sheet paths and the transcript so Claude can read them

Not affiliated with, endorsed by, or sponsored by Meta, Instagram or Anthropic.

## Default use: a local video file

```bash
python watch.py my-video.mp4
```

Typical sources: a screen recording you made, or a video you own or have permission to analyze.

**Network behavior, precisely.** Local-file mode never connects to Instagram or any video platform. It is not
"fully offline" in every case:

| Situation | Network requests |
|---|---|
| `pip install` of the dependencies | yes (PyPI; the ffmpeg binary ships inside the `imageio-ffmpeg` wheel) |
| First transcription, Whisper model not cached yet | yes: downloads `Systran/faster-whisper-small` (about 500 MB) from `huggingface.co` |
| Later runs, model cached | none observed (0 connections in my test, see below) |
| `--no-audio` | none (the model is never loaded) |

Set `HF_HUB_OFFLINE=1` to forbid Hugging Face requests entirely. Note that frames and the transcript still go
to Claude when it reads them (next sections), which is a network transfer by Claude Code, not by this script.

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
| Audio transcript | Whisper `small` on your machine | `audio.wav` in the temp work dir; transcript is printed, and also written to `transcript.txt` only with `--keep` |
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
git clone https://github.com/echno35/instagram-video-analyzer-skill.git ~/.claude/skills/instagram
cd ~/.claude/skills/instagram
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
```

`SKILL.md` calls `.venv/Scripts/python` (Windows layout); on macOS/Linux change it to `.venv/bin/python`.
Tests: `python -m unittest discover -s tests` (they generate their own synthetic video, no third-party content).

## Tested on

- **Tested:** Windows 11 Pro only, Python 3.12.10, CPU only. Local-file mode and `--download` (against a local
  HTTP server serving a self-generated video) pass the test suite there.
- **Not tested:** macOS, Linux, other Python versions, GPU/CUDA, other Whisper model sizes, and
  **downloading from Instagram with the current version of this code**. Instagram changes often and may
  block or alter what `yt-dlp` can do; no result from an earlier version carries over.
  The code is plain Python and should be portable, but that is an expectation, not a result.

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

- Claude sees sampled frames, not motion. Raise the frame rate with `--interval 1` for short clips.
- Music-only audio produces meaningless transcripts; check the printed language probability.
- No legal advice: this README is not one.
