from __future__ import annotations

import subprocess
from pathlib import Path
from PIL import Image


def make_srt(subtitles: list[str], out_path: Path, seconds: float = 2.0) -> Path:
    def ts(sec: float) -> str:
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        ms = int((sec - int(sec)) * 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    lines = []
    t = 0.0
    for i, text in enumerate(subtitles, 1):
        lines += [str(i), f"{ts(t)} --> {ts(t+seconds)}", text, ""]
        t += seconds
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def make_ffmpeg_concat_list(png_dir: Path, out_txt: Path, duration: float = 2.0) -> Path:
    files = sorted(png_dir.glob("page_*.png"), key=lambda p: int(p.stem.split("_")[1]))
    lines = []
    for f in files:
        lines.append(f"file '{f.resolve()}'")
        lines.append(f"duration {duration}")
    if files:
        lines.append(f"file '{files[-1].resolve()}'")
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    out_txt.write_text("\n".join(lines), encoding="utf-8")
    return out_txt


def make_video(png_dir: Path, out_mp4: Path, duration: float = 2.0) -> Path:
    concat = out_mp4.with_suffix(".txt")
    make_ffmpeg_concat_list(png_dir, concat, duration)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    # Automatically detect the resolution of the exported screenshots to render a pixel-perfect,
    # lossless-scaled video. If device_scale_factor=2, size is 2160x2880.
    png_files = sorted(png_dir.glob("page_*.png"))
    width, height = 2160, 2880
    if png_files:
        try:
            with Image.open(png_files[0]) as img:
                width, height = img.size
            print(f"  Detected source screenshot resolution: {width}x{height}. Exporting video in match resolution.")
        except Exception as e:
            print(f"  Warning: Failed to read screenshot size: {e}. Defaulting to {width}x{height}.")

    # -c:v libx264: encode with H.264
    # -crf 17: visually lossless quality (lower is better, 18 is visually perfect, 17 is extremely crisp)
    # -preset slow: better compression efficiency
    # -vf scale=w:h:flags=lanczos: high-quality sinc filter scaling (preserves fine detail and textures)
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat),
        "-c:v", "libx264",
        "-crf", "17",
        "-preset", "slow",
        "-pix_fmt", "yuv420p",
        "-vf", f"scale={width}:{height}:flags=lanczos",
        "-r", "30",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True)
    return out_mp4
