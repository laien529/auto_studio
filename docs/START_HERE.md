# Neue Garage Autopilot 开箱指南

这是完整自动工作流版本。

主流程：

```text
监控工信部
↓
生成选题
↓
AI生成9页内容
↓
自动匹配官方图片
↓
HTML/CSS自动排版
↓
导出9张PNG
↓
生成抖音字幕SRT
↓
可选生成MP4
```

---

# 1. 安装

```bash
cd neue-garage-autopilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

如果要生成MP4：

```bash
brew install ffmpeg
```

---

# 2. 监控工信部

```bash
python scripts/monitor_miit.py
```

输出：

```text
outputs/reports/miit_monitor_*.json
```

注意：
当前监控的是官方公告页面增量变化。
如果要查询动态“产品信息/产品分批查询”，后续需要 Playwright 深度适配。

---

# 3. 准备图片

把下载的官方图片全部放入：

```text
assets/inbox/

一键脚本详见：AUTO_ASSET_TAGGER_GUIDE.md
```

---
<!-- 
# 4. OpenAI一键生成

设置：

```bash
cp .env.example .env
export OPENAI_API_KEY="你的key"
```

运行：

```bash
python scripts/run_autopilot_openai.py
```

---

# 5. Ollama本地生成

```bash
ollama pull qwen2.5vl
python scripts/run_autopilot_ollama.py
``` -->

---
<!-- 
# 6. 用已有JSON直接出图

```bash
python scripts/run_from_existing_json.py \
  --content data/topics/sample_i3.json \
  --assets assets/library/BMW/i3 \
  --name i3_test
```

---

# 7. 输出结果

```text
outputs/images/项目名/page_1.png ... page_9.png
outputs/video/项目名.srt
outputs/video/项目名.mp4
outputs/content/项目名_canva.csv -->
```

---

# 8. 发布

小红书：
上传9张PNG。

抖音：
上传MP4或用9张PNG在剪映中二次处理。

