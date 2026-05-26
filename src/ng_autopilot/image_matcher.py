\
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

ROLE_TO_FOLDERS: Dict[str, List[str]] = {
    "cover": ["exterior", "detail", "lifestyle"],
    "opening": ["detail", "exterior"],
    "design": ["exterior", "detail"],
    "interior": ["interior"],
    "history": ["history", "exterior"],
    "technology": ["detail", "interior", "exterior"],
    "core_point": ["detail", "exterior", "lifestyle"],
    "audience": ["lifestyle", "exterior"],
    "interaction": ["detail", "exterior"],
}

KEYWORD_MAP: Dict[str, List[str]] = {
    "封面": ["cover", "front", "hero", "main", "dark"],
    "45": ["45", "front", "threequarter", "hero"],
    "前侧": ["front", "threequarter", "45"],
    "车头": ["front", "headlight", "light"],
    "灯": ["light", "headlight", "tail", "lamp"],
    "侧面": ["side", "profile"],
    "比例": ["side", "profile"],
    "内饰": ["interior", "cockpit", "dashboard", "steering"],
    "座舱": ["interior", "cockpit"],
    "中控": ["dashboard", "screen", "cockpit"],
    "历史": ["history", "archive", "e46", "f30", "g20"],
    "时间线": ["history", "archive", "timeline"],
    "平台": ["platform", "tech", "architecture"],
    "技术": ["tech", "platform", "architecture"],
    "结构": ["platform", "architecture", "tech"],
    "黑底": ["dark", "black", "detail"],
    "模糊": ["abstract", "detail", "dark"],
    "城市": ["city", "lifestyle", "night", "urban"],
    "生活": ["lifestyle", "city", "road"],
    "尾灯": ["rear", "tail", "taillight", "light"],
    "车尾": ["rear", "tail"],
    "rear": ["rear", "tail"],
    "front": ["front", "headlight"],
    "side": ["side", "profile"],
    "interior": ["interior", "cockpit", "dashboard"],
    "lifestyle": ["lifestyle", "city", "road"],
    "history": ["history", "archive"],
    "tech": ["tech", "platform"],
}


def normalize(s: str) -> str:
    return s.lower().replace("-", "_").replace(" ", "_")


def list_images(assets_dir: Path) -> List[Path]:
    return [p for p in assets_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]


def score_image(img: Path, page: dict, assets_root: Path) -> int:
    role = normalize(page.get("role", ""))
    hint = normalize(page.get("image_hint", ""))
    title = normalize(page.get("title", ""))
    name = normalize(img.stem)
    full = normalize(str(img.relative_to(assets_root)))

    score = 0
    for idx, folder in enumerate(ROLE_TO_FOLDERS.get(role, [])):
        if f"/{folder}/" in f"/{full}":
            score += max(20 - idx * 4, 8)

    if role and role in name:
        score += 8

    combined_hint = hint + " " + title
    for key, values in KEYWORD_MAP.items():
        if normalize(key) in combined_hint:
            for v in values:
                if normalize(v) in name or normalize(v) in full:
                    score += 10

    page_num = str(page.get("page", ""))
    if page_num and (f"page_{page_num}" in name or f"p{page_num}" == name):
        score += 50

    if page.get("page") == 1 and ("cover" in name or "hero" in name):
        score += 30

    return score


def match_images(content: dict, assets_root: Path, out_assets: Path, csv_path: Path) -> dict:
    images = list_images(assets_root)
    if not images:
        raise FileNotFoundError(f"没有在素材目录找到图片：{assets_root}")

    used = set()
    out_assets.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    report = []

    for page in content.get("pages", []):
        scored = []
        for img in images:
            if img in used:
                continue
            scored.append((score_image(img, page, assets_root), img))
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_img = scored[0]
        used.add(best_img)

        page_num = page.get("page")
        ext = best_img.suffix.lower()
        filename = f"page_{page_num}{ext}"
        target = out_assets / filename
        # Downscale and compress matched image using PIL (Pillow) to reduce RAM load in Chromium
        try:
            from PIL import Image
            with Image.open(best_img) as img:
                w, h = img.size
                max_dim = 2160
                if w > max_dim or h > max_dim:
                    if w >= h:
                        new_w = max_dim
                        new_h = int(h * max_dim / w)
                    else:
                        new_h = max_dim
                        new_w = int(w * max_dim / h)
                    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                
                fmt = img.format or best_img.suffix.strip('.').upper()
                if fmt == 'MPO':
                    fmt = 'JPEG'
                
                if fmt in ('JPEG', 'JPG'):
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    img.save(target, format='JPEG', quality=90)
                elif fmt == 'PNG':
                    img.save(target, format='PNG', optimize=True)
                elif fmt == 'WEBP':
                    img.save(target, format='WEBP', quality=90)
                else:
                    shutil.copy2(best_img, target)
        except Exception as e:
            print(f"  Warning: PIL image downscaling failed for {best_img.name}: {e}. Falling back to copy.")
            shutil.copy2(best_img, target)

        row = {
            "page": page_num,
            "role": page.get("role", ""),
            "title": page.get("title", ""),
            "body": page.get("body", ""),
            "image_hint": page.get("image_hint", ""),
            "image_filename": filename,
            "image_path": str(target),
            "category": best_img.parent.name,
        }
        rows.append(row)
        report.append({"page": page_num, "source": str(best_img), "target": str(target), "score": best_score})

    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    return {"rows": rows, "report": report, "csv": str(csv_path), "assets": str(out_assets)}
