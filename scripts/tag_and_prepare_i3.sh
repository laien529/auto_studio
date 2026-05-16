#!/usr/bin/env bash
set -e
python scripts/tag_assets.py \
  --inbox assets/inbox \
  --library assets/library \
  --brand BMW \
  --model i3 \
  --series "Neue Klasse" \
  --name bmw_i3
echo "Done. Tagged files are in assets/library/bmw/i3/"
