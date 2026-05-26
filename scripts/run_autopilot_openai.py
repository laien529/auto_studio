from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ng_autopilot.content_generator import generate_openai, save_content
from ng_autopilot.image_matcher import match_images
from ng_autopilot.renderer import render_html_files, export_png_with_playwright
from ng_autopilot.video import make_srt, make_video

import argparse

parser = argparse.ArgumentParser(description="Run Autopilot using OpenAI")
parser.add_argument("--name", default="bmw_i3", help="Project/output name")
parser.add_argument("--topic", default="BMW Neue Klasse i3", help="Topic for LLM to write about")
parser.add_argument("--column", default="新车档案", help="Column style name")
parser.add_argument("--angle", default="宝马终于开始真正做电动车了", help="Angle/hook for the copywriting")
parser.add_argument("--assets", default="assets/library/BMW/i3", help="Assets library directory path relative to project root")
parser.add_argument("--model", default=None, help="OpenAI model to use for content generation. If not specified, dynamically resolved from config/settings.json.")
parser.add_argument("--scale-factor", type=int, default=2, help="Device scale factor for Playwright rendering (1 for standard, 2 for Retina 2K, 3 for 3K)")
args = parser.parse_args()

if not args.model:
    try:
        settings_path = ROOT / "config" / "settings.json"
        if settings_path.exists():
            settings_data = json.loads(settings_path.read_text(encoding="utf-8"))
            args.model = settings_data.get("default_model_openai", "gpt-4.1-mini")
    except Exception:
        pass
    if not args.model:
        args.model = "gpt-4.1-mini"

PROJECT = args.name
TOPIC = args.topic
COLUMN = args.column
ANGLE = args.angle
ASSETS = ROOT / args.assets
MODEL = args.model

data = generate_openai(ROOT, TOPIC, COLUMN, ANGLE, model=MODEL)
content_path = save_content(ROOT, data, PROJECT)

matched = match_images(
    content=data,
    assets_root=ASSETS,
    out_assets=ROOT / "outputs" / "matched_assets" / PROJECT,
    csv_path=ROOT / "outputs" / "content" / f"{PROJECT}_canva.csv"
)

html_dir = render_html_files(ROOT, data, matched["rows"], PROJECT)
png_dir = ROOT / "outputs" / "images" / PROJECT
export_png_with_playwright(html_dir, png_dir, device_scale_factor=args.scale_factor)

make_srt(data.get("douyin", {}).get("subtitles", []), ROOT / "outputs" / "video" / f"{PROJECT}.srt")

try:
    make_video(png_dir, ROOT / "outputs" / "video" / f"{PROJECT}.mp4")
except Exception as e:
    print("视频生成跳过：需要安装 ffmpeg。错误：", e)

print("DONE")
print("content:", content_path)
print("images:", png_dir)
print("csv:", matched["csv"])
