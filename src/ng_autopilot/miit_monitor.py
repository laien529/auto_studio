\
from __future__ import annotations

import json
import re
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


@dataclass
class MiitItem:
    title: str
    url: str
    date: str | None
    source_page: str
    matched_keywords: list[str]


def load_settings(root: Path) -> dict:
    return json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))


def fingerprint(item: MiitItem) -> str:
    raw = f"{item.title}|{item.url}|{item.date}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def extract_items_from_page(url: str, keywords: list[str], timeout: int = 20) -> list[MiitItem]:
    headers = {
        "User-Agent": "Mozilla/5.0 NeueGarageBot/0.1 (+local personal monitor)"
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "lxml")
    items: list[MiitItem] = []

    # 官方页面常见结构：a文本 + [YYYY-MM-DD]
    page_text = soup.get_text("\n", strip=True)

    for a in soup.find_all("a"):
        title = a.get_text(" ", strip=True)
        href = a.get("href")
        if not title or not href:
            continue

        full_url = urljoin(url, href)
        parent_text = a.parent.get_text(" ", strip=True) if a.parent else title
        date_match = re.search(r"(20\d{2}[-年/.]\d{1,2}[-月/.]\d{1,2})", parent_text)
        date = date_match.group(1).replace("年", "-").replace("月", "-").replace("日", "") if date_match else None

        matched = [kw for kw in keywords if kw.lower() in title.lower() or kw.lower() in parent_text.lower()]
        if matched:
            items.append(MiitItem(
                title=title,
                url=full_url,
                date=date,
                source_page=url,
                matched_keywords=matched
            ))

    # 如果栏目页因为JS没有列出链接，至少保存页面状态
    if not items and page_text:
        matched = [kw for kw in keywords if kw.lower() in page_text.lower()]
        if matched:
            items.append(MiitItem(
                title=f"Page matched keywords: {', '.join(matched)}",
                url=url,
                date=None,
                source_page=url,
                matched_keywords=matched
            ))

    # 去重
    seen = set()
    unique = []
    for it in items:
        fp = fingerprint(it)
        if fp not in seen:
            seen.add(fp)
            unique.append(it)
    return unique


def monitor(root: Path) -> dict:
    settings = load_settings(root)
    pages = settings["miit"]["announcement_pages"]
    keywords = settings["miit"]["keywords"]

    state_path = root / "data" / "state" / "miit_seen.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    seen = set(json.loads(state_path.read_text(encoding="utf-8"))) if state_path.exists() else set()

    all_items = []
    new_items = []

    for page in pages:
        try:
            items = extract_items_from_page(page, keywords)
        except Exception as e:
            items = [MiitItem(
                title=f"ERROR fetching {page}: {e}",
                url=page,
                date=None,
                source_page=page,
                matched_keywords=["ERROR"]
            )]

        for item in items:
            all_items.append(item)
            fp = fingerprint(item)
            if fp not in seen:
                new_items.append(item)
                seen.add(fp)

    state_path.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "total_items": len(all_items),
        "new_items": [asdict(x) for x in new_items],
        "all_items": [asdict(x) for x in all_items],
    }

    out = root / "outputs" / "reports" / f"miit_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parents[2]
    result = monitor(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
