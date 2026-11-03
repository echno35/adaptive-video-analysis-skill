# instagram-skill

A Claude Code skill that lets Claude "watch" a public Instagram reel or post.
Claude cannot play video, so the skill approximates it:

1. downloads the video with `yt-dlp`
2. builds contact sheets (one frame every 2 s, 10 frames per sheet) with a bundled `ffmpeg`
3. transcribes the audio locally with `faster-whisper` (CPU)

Claude then reads the sheets and the transcript and describes what happens.

## Install

```bash
git clone <this-repo-url> ~/.claude/skills/instagram
cd ~/.claude/skills/instagram
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
```

`SKILL.md` calls `.venv/Scripts/python` (Windows layout). On macOS/Linux change it to `.venv/bin/python`.

## Use

Start a new Claude Code session and send a link such as
`https://www.instagram.com/reels/<id>/`, or run it directly:

```bash
.venv/Scripts/python watch.py "<url>" [--out DIR] [--interval 2]
```

## Limits

- Public posts only. Private accounts need a login, which this skill does not handle.
- Instagram changes often; if downloads break, run `pip install -U yt-dlp`.
- Music-only audio produces meaningless transcripts; check the printed language probability.
- The first run downloads the Whisper `small` model (about 500 MB).
- Download only content you are allowed to analyze.
