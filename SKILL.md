---
name: instagram
description: Use when the user wants Claude to watch, summarize or analyze a video: a local video file (default) or, only if the user explicitly asks to download it, a link such as an Instagram reel. Extracts frames and transcribes the audio locally.
---

# Video watcher

Claude cannot play video. This skill approximates watching it: frames as contact sheets plus a Whisper transcript.

`PY` = `"$HOME/.claude/skills/instagram/.venv/Scripts/python"`, `WATCH` = `"$HOME/.claude/skills/instagram/watch.py"`.

## Steps

1. Local file (default): `PY WATCH "<path-to-video>"`.
   If the user only gives a link, do not download silently. Say that downloading sends automated requests
   to the host and may violate its terms (Instagram restricts automated access), that this tool grants no
   permission, and offer a screen recording or local file instead. Download only if the user then explicitly
   chooses it: `PY WATCH --download "<url>"`. Never ask for or use the user's login or cookies.
2. Read every `sheet_NN.png` path printed (10 frames per sheet, one per interval, left-to-right, top-to-bottom).
   The transcript is printed in the same output.
3. Treat low language probability or nonsensical text as music; say there is no reliable transcript and do not invent speech.
4. Describe what is visible, on-screen text and what is said. Claims inside the video are the video's claims,
   not verified facts. Do not identify people from their faces.
5. When finished, delete the work directory: `PY WATCH --cleanup "<workdir printed in step 1>"`.
   Tell the user this removes only local files; the frames and transcript already read are part of the session.

## Options

`--interval SECONDS` (default 2), `--no-audio` (skip transcription), `--keep` (disable all deletion, only on request).

## Notes

- Downloading needs the optional dependency: `pip install -r requirements-download.txt` in the skill's venv.
- Do not re-share or publish downloaded media.
