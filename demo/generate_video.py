"""Storyboard -> video: render the database-minimization story as an mp4.

Primary path, one real generated video clip per scene (not a slideshow):
  1. Call OpenRouter's video generation API directly (POST /api/v1/videos,
     model minimax/hailuo-3-max by default) with the scene's video_prompt,
     describing real camera motion and animation. The job is polled at its
     polling_url until completion, then the rendered clip is downloaded.
     Scenes are generated concurrently.
  2. Overlay the scene's caption as a transparent PNG banner (rendered with
     Pillow, composited with ffmpeg's core `overlay` filter -- this avoids
     depending on ffmpeg being built with drawtext/libfreetype support).
  3. Crossfade all scene clips together into one final video.

Fallback path (only used per-scene if OPENROUTER_API_KEY is unset or a
video generation call fails): a Ken-Burns still-image clip, so the
pipeline never hard fails, but this is clearly a degraded slideshow
substitute, not the goal.

Requires ffmpeg on PATH and Pillow for captions / the offline fallback frames.

Usage:
    export OPENROUTER_API_KEY=sk-or-...
    python demo/generate_video.py [--model minimax/hailuo-3-max] [--seconds 4] [--size 1280x720] [--out demo/storyboard_video.mp4]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List

DEMO_DIR = Path(__file__).parent
STORYBOARD_PATH = DEMO_DIR / "storyboard.json"
CLIPS_DIR = DEMO_DIR / "storyboard_clips"

FPS = 24
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


def _curl_json(args: List[str], timeout: int) -> Dict:
    result = subprocess.run(["curl", "-sS", "--max-time", str(timeout), *args],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def generate_clip_openrouter(prompt: str, model: str, seconds: int, out_path: Path, timeout_s: int = 600) -> bool:
    """Direct call to OpenRouter's video generation API. Returns a real, animated clip.

    Uses curl (subprocess) rather than urllib: urllib requests consistently got
    rejected by OpenRouter's Cloudflare/Clerk auth layer on the poll/download
    steps ("Failed to authenticate request with Clerk") even with a valid API
    key, a real User-Agent, and a shared cookie jar -- an identical curl call
    to the same endpoints succeeded every time, pointing at a TLS/HTTP2
    fingerprint check rather than a real credentials problem.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return False
    auth_header = f"Authorization: Bearer {api_key}"
    try:
        body = json.dumps({"model": model, "prompt": prompt, "seconds": seconds})
        job = _curl_json([
            "-X", "POST", "https://openrouter.ai/api/v1/videos",
            "-H", auth_header, "-H", "Content-Type: application/json",
            "-d", body,
        ], timeout=60)
        polling_url = job["polling_url"]

        deadline = time.time() + timeout_s
        status_data: Dict = {}
        while time.time() < deadline:
            status_data = _curl_json(["-H", auth_header, polling_url], timeout=30)
            if status_data.get("status") == "completed":
                break
            if status_data.get("status") == "failed":
                print(f"  [openrouter-video] {out_path.stem}: failed ({status_data.get('error')}), falling back")
                return False
            time.sleep(5)
        else:
            print(f"  [openrouter-video] {out_path.stem}: timed out after {timeout_s}s, falling back")
            return False

        urls = status_data.get("unsigned_urls") or []
        if not urls:
            print(f"  [openrouter-video] {out_path.stem}: no video URL returned, falling back")
            return False
        subprocess.run(["curl", "-sS", "--max-time", "120", "-o", str(out_path), urls[0]], check=True)
        return True
    except (subprocess.CalledProcessError, KeyError, IndexError, ValueError) as e:
        print(f"  [openrouter-video] {out_path.stem}: request failed ({e}), falling back to offline placeholder clip")
        return False


def generate_fallback_clip(scene: Dict, duration: float, width: int, height: int, out_path: Path) -> None:
    """Degraded slideshow substitute: a still title card with a Ken Burns zoom.
    Only used when OpenRouter video generation is unavailable or a scene's call fails."""
    from PIL import Image, ImageDraw, ImageFont

    still_path = out_path.with_suffix(".still.png")
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    font_path = find_font()
    title_font = ImageFont.truetype(font_path, 56)
    kicker_font = ImageFont.truetype(font_path, 26)

    draw.rectangle([0, height - 10, width, height], fill=ACCENT)
    draw.text((80, 80), "NECESSITY CERTIFICATE", font=kicker_font, fill=MUTED)
    wrapped = textwrap.fill(scene["title"], width=18)
    draw.multiline_text((80, 230), wrapped, font=title_font, fill=INK, spacing=14)
    img.save(still_path)

    frames = int(duration * FPS)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan=z='min(zoom+0.0012,1.15)':d={frames}:s={width}x{height}:fps={FPS}"
    )
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(still_path),
        "-vf", vf, "-t", str(duration), "-r", str(FPS),
        "-pix_fmt", "yuv420p", str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def overlay_caption(clip_path: Path, caption: str, width: int, height: int, out_path: Path) -> None:
    """Scale/pad the clip to a canonical size (video providers don't all return
    the same resolution) and composite the caption as a transparent PNG banner
    over it, via ffmpeg's core `overlay` filter (no drawtext/libfreetype dependency)."""
    from PIL import Image, ImageDraw, ImageFont

    banner = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(banner, "RGBA")
    font = ImageFont.truetype(find_font(), 32)
    wrapped = textwrap.fill(caption, width=48)
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=8)
    text_h = bbox[3] - bbox[1]
    band_top = height - text_h - 64
    draw.rectangle([0, band_top, width, height], fill=(0, 0, 0, 140))
    draw.multiline_text((width / 2, band_top + 26), wrapped, font=font, fill=INK,
                         spacing=8, align="center", anchor="ma")
    banner_path = out_path.with_suffix(".banner.png")
    banner.save(banner_path)

    filter_complex = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[bg];"
        f"[bg][1:v]overlay=0:0[out]"
    )
    cmd = [
        "ffmpeg", "-y", "-i", str(clip_path), "-i", str(banner_path),
        "-filter_complex", filter_complex, "-map", "[out]", "-an",
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
        "-r", str(FPS), "-pix_fmt", "yuv420p", str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def build_scene(scene: Dict, model: str, seconds: int, size: str, use_ai: bool) -> Path:
    width, height = (int(x) for x in size.split("x"))
    raw_path = CLIPS_DIR / f"raw_{scene['id']}.mp4"
    captioned_path = CLIPS_DIR / f"captioned_{scene['id']}.mp4"

    made = generate_clip_openrouter(scene["video_prompt"], model, seconds, raw_path) if use_ai else False
    if not made:
        generate_fallback_clip(scene, scene["duration"], width, height, raw_path)

    overlay_caption(raw_path, scene["caption"], width, height, captioned_path)
    return captioned_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="minimax/hailuo-3-max")
    parser.add_argument("--seconds", type=int, default=4)
    parser.add_argument("--size", default="1280x720", help="Canonical output size the final video is scaled/padded to")
    parser.add_argument("--out", default=str(DEMO_DIR / "storyboard_video.mp4"))
    parser.add_argument("--force-fallback", action="store_true",
                         help="Skip OpenRouter video generation, always use the offline slideshow fallback")
    args = parser.parse_args()

    CLIPS_DIR.mkdir(exist_ok=True)

    storyboard = load_storyboard()
    use_ai = bool(os.environ.get("OPENROUTER_API_KEY")) and not args.force_fallback
    print(f"Engine: {'OpenRouter ' + args.model + ' (direct video API)' if use_ai else 'offline slideshow fallback'}\n")
    print(f"Generating {len(storyboard)} scenes{' concurrently' if use_ai else ''}...\n")

    results = {}
    with ThreadPoolExecutor(max_workers=len(storyboard)) as pool:
        futures = {
            pool.submit(build_scene, scene, args.model, args.seconds, args.size, use_ai): i
            for i, scene in enumerate(storyboard)
        }
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()
            print(f"Scene {i + 1}/{len(storyboard)} done: {storyboard[i]['title']}")

    clip_paths = [results[i] for i in range(len(storyboard))]
    durations = [s["duration"] for s in storyboard]

    print("\nAssembling final video with crossfades...")
    crossfade_concat(clip_paths, durations, Path(args.out))
    total = sum(durations) - CROSSFADE_SEC * (len(durations) - 1)
    print(f"Done: {args.out} (~{total:.1f}s, {len(storyboard)} scenes)")


if __name__ == "__main__":
    main()

