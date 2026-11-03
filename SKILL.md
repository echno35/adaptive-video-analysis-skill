---
name: instagram
description: Use when the user sends an Instagram reel/post link (instagram.com/reel, /reels, /p) and wants Claude to watch, summarize or analyze the video. Downloads it, extracts frames and transcribes the audio.
---

# Instagram video watcher

Claude cannot play video. This skill approximates watching it: frames as contact sheets plus a Whisper transcript.

## Steps

1. Run (the venv lives next to this file):

   ```bash
   "$HOME/.claude/skills/instagram/.venv/Scripts/python" "$HOME/.claude/skills/instagram/watch.py" "<url>"
   ```

   Optional: `--interval 1` for denser frames on short clips, `--out DIR` to choose the output folder (default `%TEMP%/instagram-watch`).

2. Read every `sheet_NN.png` path it prints (each sheet = 10 frames, one per interval, left-to-right, top-to-bottom).
3. Combine with the transcript. If the language probability is low or the text is nonsense, treat the audio as music and say there is no reliable transcript; do not invent speech.
4. Report what is visible, on-screen text, what is said, and caption/uploader only if shown in the output. Claims made in the video (e.g. which tool made something) are the video's claims, not verified facts.

## Notes

- Public posts only; private accounts or login walls fail in yt-dlp. Do not ask for or enter the user's credentials; tell them it needs a public link.
- If yt-dlp breaks (Instagram changes often): `"$HOME/.claude/skills/instagram/.venv/Scripts/python" -m pip install -U yt-dlp`.
- Files are downloaded for analysis only; do not re-share or publish them.
