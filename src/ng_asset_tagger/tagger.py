
from __future__ import annotations
import csv, hashlib, json, re, shutil, os, tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Tuple
from PIL import Image

try:
    import ollama
except ImportError:
    ollama = None  # type: ignore

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

def _get_compressed_image(img_path: Path) -> str:
    """
    If the image is too large, resize and compress it to a temporary JPEG
    to prevent Ollama OOM / 502 Bad Gateway errors.
    Returns the path of the image to send to Ollama.
    """
    # If the file is small enough (e.g., < 1.5MB), send it directly
    if img_path.stat().st_size < 1.5 * 1024 * 1024:
        return str(img_path)

    try:
        with Image.open(img_path) as img:
            # Maintain aspect ratio, max dimension 1024
            img.thumbnail((1024, 1024))
            
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            temp_path = temp_file.name
            temp_file.close()
            
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
                
            img.save(temp_path, "JPEG", quality=85)
            print(f"  Image too large ({img_path.stat().st_size / 1024 / 1024:.2f} MB). Compressed to {Path(temp_path).stat().st_size / 1024:.1f} KB for LLM.")
            return temp_path
    except Exception as e:
        print(f"  Warning: Failed to compress image {img_path.name}: {e}. Sending original.")
        return str(img_path)

def _classify_image_with_vision_model(
    api_base: str | None, img_path: Path, cfg: dict, brand: str, model: str, model_name: str
) -> Tuple[str, str, int]:
    """
    Classifies an image using a vision model (e.g., GPT-4 Vision).
    Returns a tuple of (category, tag, score).
    """
    categories = list(cfg["keywords"].keys())
    tags = list(cfg["tags"].keys())

    prompt = f"""
You are an expert automotive photo editor. Your task is to classify an image of a car.
The car is a {brand} {model}.

Analyze the provided image and classify it according to these rules:
1.  Choose the single best **category** from this list: {', '.join(categories)}
2.  Choose the single best **tag** from this list: {', '.join(tags)}

Return your answer as a single, valid JSON object with two keys: "category" and "tag".
For example: {{"category": "exterior", "tag": "front"}}
Do not include any other text or explanations in your response.
"""

    try:
        from pydantic import BaseModel
    except ImportError:
        raise ImportError("The 'pydantic' Python library is not installed. Please run 'pip install pydantic'.")

    class ImageClassification(BaseModel):
        category: str
        tag: str

    temp_path = None
    try:
        temp_path = _get_compressed_image(img_path)
        
        if api_base:
            # Ollama SDK expects the base host without the OpenAI-compatible '/v1' suffix
            host = api_base[:-3] if api_base.endswith("/v1") else api_base
            client = ollama.Client(host=host)
        else:
            client = ollama.Client()
        
        # Dynamically limit thread count and context size to avoid memory swap and CPU freezing
        import os
        num_cores = os.cpu_count() or 4
        num_threads = max(1, num_cores // 2)
        num_ctx = 2048
        try:
            settings_path = Path(__file__).resolve().parents[2] / "config" / "settings.json"
            if settings_path.exists():
                settings_data = json.loads(settings_path.read_text(encoding="utf-8"))
                num_threads = settings_data.get("ollama_num_thread", num_threads)
                num_ctx = settings_data.get("ollama_num_ctx", num_ctx)
        except Exception:
            pass

        response = client.chat(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [temp_path]
                }
            ],
            format=ImageClassification.model_json_schema(),
            options={
                "num_thread": num_threads,
                "num_ctx": num_ctx
            }
        )
        result_text = response.get("message", {}).get("content", "")
        try:
            data = ImageClassification.model_validate_json(result_text)
            category = data.category if data.category in categories else "unknown"
            tag = data.tag if data.tag in tags else "unknown"
            return category, tag, 10
        except Exception as parse_error:
            print(f"Warning: Could not parse JSON from LLM response for {img_path.name}: {result_text}\nError: {parse_error}")
            return "unknown", "unknown", 0
    except Exception as e:
        print(f"Error classifying image {img_path.name} with vision model: {e}")
        return "unknown", "unknown", 0
    finally:
        if temp_path and temp_path != str(img_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass

def next_available_path(path: Path) -> Path:
    if not path.exists():
        return path
    i = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{i}{path.suffix.lower()}")
        if not candidate.exists():
            return candidate
        i += 1

def tag_assets(root: Path, inbox: Path, library: Path, brand=None, model=None, series=None, move=False, use_vision=False, vision_model=None) -> List[AssetRecord]:
    cfg = load_config(root)
    brand = brand or cfg["default_brand"]
    model = model or cfg["default_model"]
    series = series or cfg["default_series"]

    images = scan_images(inbox, set(cfg["image_extensions"]))
    total = len(images)
    print(f"Scanning inbox: found {total} images to process.")
    records, seen_hashes, counters, api_base, model_to_use = [], set(), {}, None, None

    for idx, img_path in enumerate(images, 1):
        print(f"[{idx}/{total}] Processing: {img_path.name}...")
        try:
            w, h, ratio = get_image_info(img_path)
            sha1 = file_sha1(img_path)
        except Exception as e:
            print(f"  Error reading image info: {e}")
            continue

        if sha1 in seen_hashes:
            print(f"  Skipped (duplicate image)")
            continue
        seen_hashes.add(sha1)

        category, tag, score = "unknown", "unknown", 0
        vision_failed = False

        if use_vision:
            try:
                if api_base is None:
                    if ollama is None:
                        raise ImportError("The 'ollama' Python library is not installed. Please run 'pip install ollama'.")

                    vision_config = cfg.get("vision_config")
                    if not vision_config:
                        raise ValueError("'vision_config' section not found in tagger_config.json. It's required for --vision mode.")

                    api_base = vision_config.get("api_base")
                    if vision_model:
                        model_to_use = vision_model
                    else:
                        model_to_use = None
                        try:
                            settings_path = root / "config" / "settings.json"
                            if settings_path.exists():
                                settings_data = json.loads(settings_path.read_text(encoding="utf-8"))
                                model_to_use = settings_data.get("default_model_vision")
                        except Exception:
                            pass
                        
                        if not model_to_use:
                            model_to_use = vision_config.get("model")
                            
                        if not model_to_use:
                            raise ValueError("'model' must be specified in 'vision_config' or 'settings.json'.")

                print(f"  Calling vision model ({model_to_use})...")
                category, tag, score = _classify_image_with_vision_model(api_base, img_path, cfg, brand, model, model_name=model_to_use)
                if category == "unknown" or tag == "unknown":
                    vision_failed = True
            except Exception as e:
                print(f"  Vision model call failed: {e}")
                vision_failed = True

        # Fallback to keyword heuristics if vision fails, or if not using vision
        if not use_vision or vision_failed:
            if use_vision:
                print(f"  Warning: Vision model failed or returned 'unknown'. Falling back to keyword heuristics...")
            category, c_score = infer_category(img_path, cfg, w, h)
            tag, t_score = infer_tag(img_path, cfg, category)
            score = c_score + t_score

        print(f"  Result -> category: {category}, tag: {tag}, score: {score}")

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
            width=w, height=h, aspect_ratio=ratio, score=score, sha1=sha1
        ))

    if use_vision and model_to_use:
        try:
            print(f"  Unloading vision model ({model_to_use}) to free memory...")
            host = api_base[:-3] if (api_base and api_base.endswith("/v1")) else api_base
            client = ollama.Client(host=host) if host else ollama.Client()
            client.chat(model=model_to_use, keep_alive=0)
        except Exception as e:
            print(f"  Warning: Failed to unload vision model: {e}")

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
