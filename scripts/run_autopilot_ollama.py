\
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ng_autopilot.content_generator import generate_ollama, save_content
from ng_autopilot.image_matcher import match_images
from ng_autopilot.renderer import render_html_files, export_png_with_playwright
from ng_autopilot.video import make_srt, make_video

PROJECT = "bmw_i3"
TOPIC = "BMW Neue Klasse i3"
COLUMN = "新车档案"
ANGLE = "宝马终于开始真正做电动车了"
ASSETS = ROOT / "assets" / "library" / "BMW" / "i3"

data = generate_ollama(ROOT, TOPIC, COLUMN, ANGLE)
content_path = save_content(ROOT, data, PROJECT)

matched = match_images(
    content=data,
    assets_root=ASSETS,
    out_assets=ROOT / "outputs" / "matched_assets" / PROJECT,
    csv_path=ROOT / "outputs" / "content" / f"{PROJECT}_canva.csv"
)

html_dir = render_html_files(ROOT, data, matched["rows"], PROJECT)
png_dir = ROOT / "outputs" / "images" / PROJECT
export_png_with_playwright(html_dir, png_dir)

make_srt(data.get("douyin", {}).get("subtitles", []), ROOT / "outputs" / "video" / f"{PROJECT}.srt")

try:
    make_video(png_dir, ROOT / "outputs" / "video" / f"{PROJECT}.mp4")
except Exception as e:
    print("视频生成跳过：需要安装 ffmpeg。错误：", e)

print("DONE")
print("content:", content_path)
print("images:", png_dir)
print("csv:", matched["csv"])
