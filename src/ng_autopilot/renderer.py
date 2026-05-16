\
from __future__ import annotations

import json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader


def render_html_files(root: Path, content: dict, matched_rows: list[dict], project_name: str) -> Path:
    html_out = root / "outputs" / "html" / project_name
    html_out.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(root / "templates" / "html")))
    template = env.get_template("page.html")

    css_path = root / "templates" / "css" / "style.css"
    css = css_path.read_text(encoding="utf-8")

    for row in matched_rows:
        page = next(p for p in content["pages"] if int(p["page"]) == int(row["page"]))
        html = template.render(
            page=page,
            row=row,
            css=css,
            image_path=Path(row["image_path"]).resolve().as_uri(),
            account_name="NEUE GARAGE",
        )
        (html_out / f"page_{page['page']}.html").write_text(html, encoding="utf-8")

    return html_out


def export_png_with_playwright(html_dir: Path, png_dir: Path, width: int = 1080, height: int = 1440) -> None:
    from playwright.sync_api import sync_playwright

    png_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(html_dir.glob("page_*.html"), key=lambda p: int(p.stem.split("_")[1]))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        for f in files:
            page.goto(f.resolve().as_uri(), wait_until="networkidle")
            page.screenshot(path=str(png_dir / f"{f.stem}.png"), full_page=True)
        browser.close()
