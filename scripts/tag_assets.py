
#!/usr/bin/env python3
from pathlib import Path
import argparse, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ng_asset_tagger.tagger import tag_assets, write_reports

parser = argparse.ArgumentParser()
parser.add_argument("--inbox", default="assets/inbox")
parser.add_argument("--library", default="assets/library")
parser.add_argument("--brand", default=None)
parser.add_argument("--model", default=None)
parser.add_argument("--series", default=None)
parser.add_argument("--name", default="project")
parser.add_argument("--move", action="store_true")
parser.add_argument("--vision", action="store_true", help="Use vision model for tagging instead of keyword heuristics.")
args = parser.parse_args()

records = tag_assets(
    root=ROOT,
    inbox=ROOT / args.inbox,
    library=ROOT / args.library,
    brand=args.brand,
    model=args.model,
    series=args.series,
    move=args.move,
    use_vision=args.vision,
)
reports = write_reports(records, ROOT / "outputs" / "reports", args.name)
print("DONE")
print(f"Tagged assets: {len(records)}")
for k, v in reports.items():
    print(f"{k}: {v}")
