from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ng_autopilot.content_generator import generate_ollama, save_content
from ng_autopilot.image_matcher import match_images
from ng_autopilot.renderer import render_html_files, export_png_with_playwright
from ng_autopilot.video import make_srt, make_video

import argparse

parser = argparse.ArgumentParser(description="Run Autopilot using Ollama")
parser.add_argument("--name", default="bmw_i3", help="Project/output name")
parser.add_argument("--topic", default="BMW Neue Klasse i3", help="Topic for LLM to write about")
parser.add_argument("--column", default="新车档案", help="Column style name")
parser.add_argument("--angle", default="宝马终于开始真正做电动车了", help="Angle/hook for the copywriting")
parser.add_argument("--assets", default="assets/library/BMW/i3", help="Assets library directory path relative to project root")
parser.add_argument("--model", default="qwen2.5vl", help="Ollama model to use for content generation")
parser.add_argument("--scale-factor", type=int, default=2, help="Device scale factor for Playwright rendering (1 for standard, 2 for Retina 2K, 3 for 3K)")
args = parser.parse_args()

PROJECT = args.name
TOPIC = args.topic
COLUMN = args.column
ANGLE = args.angle
ASSETS = ROOT / args.assets
MODEL = args.model

print("=" * 60)
print(f"Starting Autopilot Pipeline for: {PROJECT}")
print("=" * 60)

print(f"\n1. Generating content using Ollama model ({MODEL})... (This can take 1-5 minutes depending on hardware)")
try:
    data = generate_ollama(ROOT, TOPIC, COLUMN, ANGLE, model=MODEL)
except Exception as e:
    print(f"   Error: LLM content generation failed! Details: {e}")
    sys.exit(1)
content_path = save_content(ROOT, data, PROJECT)
print(f"   DONE: Content JSON saved to {content_path}")

print("\n2. Matching assets with generated content...")
matched = match_images(
    content=data,
    assets_root=ASSETS,
    out_assets=ROOT / "outputs" / "matched_assets" / PROJECT,
    csv_path=ROOT / "outputs" / "content" / f"{PROJECT}_canva.csv"
)
print(f"   DONE: Matched assets to {ROOT / 'outputs' / 'matched_assets' / PROJECT}")

print("\n3. Rendering HTML templates...")
html_dir = render_html_files(ROOT, data, matched["rows"], PROJECT)
print(f"   DONE: HTML templates rendered to {html_dir}")

print("\n4. Exporting PNG images using Playwright...")
png_dir = ROOT / "outputs" / "images" / PROJECT
export_png_with_playwright(html_dir, png_dir, device_scale_factor=args.scale_factor)
print(f"   DONE: Exported images to {png_dir}")

print("\n5. Generating subtitles (SRT)...")
srt_path = ROOT / "outputs" / "video" / f"{PROJECT}.srt"
make_srt(data.get("douyin", {}).get("subtitles", []), srt_path)
print(f"   DONE: Subtitles saved to {srt_path}")

print("\n6. Rendering MP4 video...")
mp4_path = ROOT / "outputs" / "video" / f"{PROJECT}.mp4"
try:
    make_video(png_dir, mp4_path)
    print(f"   DONE: Video saved to {mp4_path}")
except Exception as e:
    print("   Video generation SKIPPED (ffmpeg required). Error:", e)

print("\n" + "=" * 60)
print("ALL PIPELINE STEPS COMPLETED!")
print("=" * 60)
print("content:", content_path)
print("images:", png_dir)
print("csv:", matched["csv"])
