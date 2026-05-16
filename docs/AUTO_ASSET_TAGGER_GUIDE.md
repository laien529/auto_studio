# Auto Asset Tagger 使用指南

这个模块把“原始官方图片”自动整理成可被 Autopilot 使用的素材库。

## 1. 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 放图片

把下载的官方图片全部放入：

```text
assets/inbox/
```

## 3. 自动分类 + 命名

```bash
python scripts/tag_assets.py \
  --inbox assets/inbox \
  --library assets/library \
  --brand BMW \
  --model i3 \
  --series "Neue Klasse" \
  --name bmw_i3
```

## 4. 输出结果

```text
assets/library/bmw/i3/
├── exterior/
├── interior/
├── detail/
├── lifestyle/
├── history/
└── unknown/
```

示例命名：

```text
bmw_i3_exterior_cover_01.jpg
bmw_i3_interior_cockpit_01.jpg
bmw_i3_detail_rear_01.jpg
```

## 5. 查看报告

```text
outputs/reports/bmw_i3_assets_report.md
outputs/reports/bmw_i3_assets.csv
outputs/reports/bmw_i3_assets.json
```

## 6. 和 Autopilot 连接

把生成的素材库给 Autopilot 用：

```bash
python scripts/run_from_existing_json.py \
  --content data/topics/sample_i3.json \
  --assets assets/library/bmw/i3 \
  --name i3_test
```

## 7. 当前版本边界

第一版使用“文件名 + 目录 + 图片比例”规则，不调用视觉大模型。

如果文件全是 `001.jpg / 002.jpg`，且没有目录信息，可能进入 `unknown`。

提高准确率的方法：

```text
front_001.jpg
side_002.jpg
interior_003.jpg
taillight_004.jpg
city_005.jpg
```

后续可升级：
- CLIP 视觉语义识别
- BLIP 图片描述
- 自动封面评分
- 智能裁切
