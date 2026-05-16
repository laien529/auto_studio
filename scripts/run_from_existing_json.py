\
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ng_autopilot.image_matcher import match_images
from ng_autopilot.renderer import render_html_files, export_png_with_playwright
from ng_autopilot.video import make_srt, make_video

parser = argparse.ArgumentParser()
parser.add_argument("--content", required=True)
parser.add_argument("--assets", required=True)
parser.add_argument("--name", default="project")
args = parser.parse_args()

data = json.loads(Path(args.content).read_text(encoding="utf-8"))

matched = match_images(
    content=data,
    assets_root=Path(args.assets),
    out_assets=ROOT / "outputs" / "matched_assets" / args.name,
    csv_path=ROOT / "outputs" / "content" / f"{args.name}_canva.csv"
)

html_dir = render_html_files(ROOT, data, matched["rows"], args.name)
png_dir = ROOT / "outputs" / "images" / args.name
export_png_with_playwright(html_dir, png_dir)
make_srt(data.get("douyin", {}).get("subtitles", []), ROOT / "outputs" / "video" / f"{args.name}.srt")

try:
    make_video(png_dir, ROOT / "outputs" / "video" / f"{args.name}.mp4")
except Exception as e:
    print("视频生成跳过：需要安装 ffmpeg。错误：", e)

print("DONE")
print("images:", png_dir)
