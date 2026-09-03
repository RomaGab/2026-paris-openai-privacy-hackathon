"""Storyboard -> video: render the database-minimization story as an mp4.

For each scene in storyboard.json:
  1. Generate an illustration for the scene's image_prompt via OpenRouter
     (an image-capable model, e.g. google/gemini-2.5-flash-image).
     If OPENROUTER_API_KEY is not set or the call fails, fall back to a
     locally rendered placeholder card in the same visual style as
     demo/index.html, so the pipeline always produces a video.
  2. Turn the still image into a short Ken-Burns clip with the scene's
     caption burned in (ffmpeg zoompan + drawtext).
  3. Crossfade all scene clips together into one final video.

Requires ffmpeg on PATH and Pillow for the offline fallback frames.

Usage:
    export OPENROUTER_API_KEY=sk-or-...   # optional, else offline fallback frames
    python demo/generate_video.py [--model google/gemini-2.5-flash-image] [--out demo/storyboard_video.mp4]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

DEMO_DIR = Path(__file__).parent
STORYBOARD_PATH = DEMO_DIR / "storyboard.json"
FRAMES_DIR = DEMO_DIR / "storyboard_frames"
CLIPS_DIR = DEMO_DIR / "storyboard_clips"

WIDTH, HEIGHT, FPS = 1280, 720, 25
CROSSFADE_SEC = 0.6

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial.ttf",
]

# Matches demo/index.html's palette.
BG = (11, 15, 20)
INK = (232, 237, 243)
ACCENT = (55, 230, 160)
MUTED = (138, 151, 168)


def load_storyboard() -> List[Dict]:
    return json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))


def find_font() -> str:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    raise FileNotFoundError("No usable TTF font found; edit FONT_CANDIDATES in generate_video.py")


def generate_image_openrouter(prompt: str, model: str, out_path: Path) -> bool:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return False
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/RomaGab/2026-paris-openai-privacy-hackathon",
            "X-Title": "Necessity Certificate storyboard",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
        images = data["choices"][0]["message"].get("images") or []
        if not images:
            print(f"  [openrouter] no image returned for prompt, falling back: {prompt[:60]}...")
            return False
        data_url = images[0]["image_url"]["url"]
        _, b64 = data_url.split(",", 1)
        out_path.write_bytes(base64.b64decode(b64))
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, ValueError) as e:
        print(f"  [openrouter] request failed ({e}), falling back to offline placeholder")
        return False


def generate_placeholder(scene: Dict, out_path: Path) -> None:
    """Offline fallback: a dark title card in the deck's own visual style."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    font_path = find_font()
    title_font = ImageFont.truetype(font_path, 64)
    kicker_font = ImageFont.truetype(font_path, 28)

    draw.rectangle([0, HEIGHT - 10, WIDTH, HEIGHT], fill=ACCENT)
    draw.text((90, 90), "NECESSITY CERTIFICATE", font=kicker_font, fill=MUTED)

    wrapped = textwrap.fill(scene["title"], width=18)
    draw.multiline_text((90, 260), wrapped, font=title_font, fill=INK, spacing=14)

    img.save(out_path)


def burn_caption(image_path: Path, caption: str, out_path: Path) -> None:
    """Composite the caption onto the frame with Pillow so the video pipeline
    never depends on ffmpeg being built with drawtext/libfreetype support."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(image_path).convert("RGB")
    img = img.resize((WIDTH, HEIGHT)) if img.size != (WIDTH, HEIGHT) else img
    draw = ImageDraw.Draw(img, "RGBA")
    font = ImageFont.truetype(find_font(), 34)

    wrapped = textwrap.fill(caption, width=42)
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=8)
    text_h = bbox[3] - bbox[1]
    band_top = HEIGHT - text_h - 70
    draw.rectangle([0, band_top, WIDTH, HEIGHT], fill=(0, 0, 0, 140))
    draw.multiline_text((WIDTH / 2, band_top + 30), wrapped, font=font, fill=INK,
                         spacing=8, align="center", anchor="ma")
    img.save(out_path)


def render_scene_clip(image_path: Path, duration: float, out_path: Path) -> None:
    frames = int(duration * FPS)
    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        f"zoompan=z='min(zoom+0.0012,1.15)':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"
    )
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-vf", vf, "-t", str(duration), "-r", str(FPS),
        "-pix_fmt", "yuv420p", str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def crossfade_concat(clip_paths: List[Path], durations: List[float], out_path: Path) -> None:
    inputs = []
    for p in clip_paths:
        inputs += ["-i", str(p)]

    filter_parts = []
    prev_label = "0:v"
    current_duration = durations[0]
    for i in range(1, len(clip_paths)):
        offset = current_duration - CROSSFADE_SEC
        new_label = f"v{i}"
        filter_parts.append(
            f"[{prev_label}][{i}:v]xfade=transition=fade:duration={CROSSFADE_SEC}:offset={offset}[{new_label}]"
        )
        current_duration = current_duration + durations[i] - CROSSFADE_SEC
        prev_label = new_label

    filter_complex = ";".join(filter_parts)
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{prev_label}]",
        "-pix_fmt", "yuv420p", str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="google/gemini-2.5-flash-image")
    parser.add_argument("--out", default=str(DEMO_DIR / "storyboard_video.mp4"))
    parser.add_argument("--force-fallback", action="store_true", help="Skip OpenRouter, always use offline placeholder frames")
    args = parser.parse_args()

    FRAMES_DIR.mkdir(exist_ok=True)
    CLIPS_DIR.mkdir(exist_ok=True)

    storyboard = load_storyboard()
    use_ai = bool(os.environ.get("OPENROUTER_API_KEY")) and not args.force_fallback
    print(f"Engine: {'OpenRouter (' + args.model + ')' if use_ai else 'offline placeholder frames'}\n")

    clip_paths, durations = [], []
    for i, scene in enumerate(storyboard):
        frame_path = FRAMES_DIR / f"{i:02d}_{scene['id']}.png"
        clip_path = CLIPS_DIR / f"{i:02d}_{scene['id']}.mp4"

        print(f"Scene {i + 1}/{len(storyboard)}: {scene['title']}")
        made = generate_image_openrouter(scene["image_prompt"], args.model, frame_path) if use_ai else False
        if not made:
            generate_placeholder(scene, frame_path)

        captioned_path = FRAMES_DIR / f"{i:02d}_{scene['id']}_captioned.png"
        burn_caption(frame_path, scene["caption"], captioned_path)

        render_scene_clip(captioned_path, scene["duration"], clip_path)
        clip_paths.append(clip_path)
        durations.append(scene["duration"])

    print("\nAssembling final video with crossfades...")
    crossfade_concat(clip_paths, durations, Path(args.out))
    total = sum(durations) - CROSSFADE_SEC * (len(durations) - 1)
    print(f"Done: {args.out} (~{total:.1f}s, {len(storyboard)} scenes)")


if __name__ == "__main__":
    main()
