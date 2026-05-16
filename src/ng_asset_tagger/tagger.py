
from __future__ import annotations
import csv, hashlib, json, re, shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Tuple
from PIL import Image

@dataclass
class AssetRecord:
    original_path: str
    new_path: str
    brand: str
    model: str
    series: str
    category: str
    tag: str
    width: int
    height: int
    aspect_ratio: float
    score: int
    sha1: str

def load_config(root: Path) -> dict:
    return json.loads((root / "config" / "tagger_config.json").read_text(encoding="utf-8"))

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", s)
    return s.strip("_") or "unknown"

def file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def get_image_info(path: Path) -> Tuple[int, int, float]:
    with Image.open(path) as img:
        w, h = img.size
    return w, h, round(w / h, 4) if h else 0

def score_by_keywords(text: str, keyword_map: Dict[str, List[str]]) -> Dict[str, int]:
    text_l = text.lower()
    scores = {k: 0 for k in keyword_map}
    for category, keywords in keyword_map.items():
        for kw in keywords:
            if kw.lower() in text_l:
                scores[category] += 10
    return scores

def infer_category(path: Path, cfg: dict, width: int, height: int) -> Tuple[str, int]:
    text = str(path).lower()
    scores = score_by_keywords(text, cfg["keywords"])
    ratio = width / height if height else 1
    if ratio > 1.35:
        scores["exterior"] += 2
        scores["lifestyle"] += 1
    if ratio < 0.9:
        scores["detail"] += 1
    category, score = max(scores.items(), key=lambda x: x[1])
    return (category, score) if score > 0 else ("unknown", 0)

def infer_tag(path: Path, cfg: dict, category: str) -> Tuple[str, int]:
    text = str(path).lower()
    scores = score_by_keywords(text, cfg["tags"])
    if category == "interior":
        scores["cockpit"] += 3
    elif category == "history":
        scores["history_archive"] += 3
    elif category == "lifestyle":
        scores["city_lifestyle"] += 3
    elif category == "detail":
        scores["front"] += 1
    elif category == "exterior":
        scores["cover"] += 1
    tag, score = max(scores.items(), key=lambda x: x[1])
    return (tag, score) if score > 0 else (category, 0)

def scan_images(inbox: Path, exts: set[str]) -> List[Path]:
    return [p for p in inbox.rglob("*") if p.is_file() and p.suffix.lower() in exts]

def next_available_path(path: Path) -> Path:
    if not path.exists():
        return path
    i = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not candidate.exists():
            return candidate
        i += 1

def tag_assets(root: Path, inbox: Path, library: Path, brand=None, model=None, series=None, move=False) -> List[AssetRecord]:
    cfg = load_config(root)
    brand = brand or cfg["default_brand"]
    model = model or cfg["default_model"]
    series = series or cfg["default_series"]

    images = scan_images(inbox, set(cfg["image_extensions"]))
    records, seen_hashes, counters = [], set(), {}

    for img_path in images:
        try:
            w, h, ratio = get_image_info(img_path)
            sha1 = file_sha1(img_path)
        except Exception:
            continue

        if sha1 in seen_hashes:
            continue
        seen_hashes.add(sha1)

        category, c_score = infer_category(img_path, cfg, w, h)
        tag, t_score = infer_tag(img_path, cfg, category)

        key = f"{category}_{tag}"
        counters[key] = counters.get(key, 0) + 1
        idx = f"{counters[key]:02d}"

        stem = cfg["rename_pattern"].format(
            brand=slugify(brand), model=slugify(model), series=slugify(series),
            category=slugify(category), tag=slugify(tag), index=idx
        )
        target_dir = library / slugify(brand) / slugify(model) / category
        target_dir.mkdir(parents=True, exist_ok=True)
        target = next_available_path(target_dir / f"{stem}{img_path.suffix.lower()}")

        if move:
            shutil.move(str(img_path), str(target))
        else:
            shutil.copy2(img_path, target)

        records.append(AssetRecord(
            original_path=str(img_path), new_path=str(target),
            brand=brand, model=model, series=series, category=category, tag=tag,
            width=w, height=h, aspect_ratio=ratio, score=c_score + t_score, sha1=sha1
        ))
    return records

def write_reports(records: List[AssetRecord], out_dir: Path, name: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = [asdict(r) for r in records]
    json_path = out_dir / f"{name}_assets.json"
    csv_path = out_dir / f"{name}_assets.csv"
    md_path = out_dir / f"{name}_assets_report.md"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if data:
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            writer.writeheader()
            writer.writerows(data)
    else:
        csv_path.write_text("", encoding="utf-8")
    lines = ["# Auto Asset Tagger Report", "", f"Total assets: {len(records)}", ""]
    for r in records:
        lines.append(f"- `{r.original_path}` → `{r.new_path}` / {r.category} / {r.tag} / score={r.score}")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)}
