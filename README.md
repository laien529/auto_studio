# 🚗 Neue Garage Autopilot (Auto Studio) 智能自媒体生产线

欢迎来到 **Neue Garage Autopilot (Auto Studio)** 汽车自媒体全自动创意出片工厂！本工作流实现了从工信部新车公告监控、多模态智能图片打标、本地 AI 文案创作，到 HTML/CSS 排版、Playwright 2K 视网膜级截图、SRT 字幕生成和 MP4 视频合成的端到端自动化。

---

## ⚡ 核心自动化工作流程
```text
  【工信部新车监控】 (scripts/monitor_miit.py)
         ↓ (发现选题)
  【原始素材放入 inbox】 (assets/inbox/)
         ↓ (一键触发)
  【 Stage 1: 图像多模态打标与归档 】 (动态压缩大图，模型分类归档，输出 Tagger 报表)
         ↓
  【 Stage 2: 文本大模型文案创作 】 (自动撰写小红书/抖音风格文案，智能匹配库内图片)
         ↓
  【 Stage 3: HTML 自动排版与 Playwright 渲染 】 (以 Retina 2K 双倍高 DPI 渲染图片与文字)
         ↓
  【 Stage 4: 视网膜截图与广播级视频合成 】 (导出 2160x2880 无损图片与低损超清 H.264 视频)
```

---

## 🚀 1. 快速准备 (3分钟极速上手)

### 环境安装
```bash
# 1. 创建并激活虚拟环境
python3 -m venv venv
source venv/bin/activate

# 2. 安装所有 Python 依赖
pip install -r config/requirements.txt

# 3. 安装 Playwright 无头浏览器内核
python -m playwright install chromium
```

### 视频渲染依赖 (可选，若要合成 MP4)
若要在生产完毕后直接合成 `.mp4` 视频，请在 Mac 系统中安装 `ffmpeg`：
```bash
brew install ffmpeg
```

---

## 🖥️ 2. H5 可视化控制台 (Web Dashboard - 强烈推荐)

我们为不想记忆复杂命令的创作者提供了一个**极具科技感、超凡视觉体验的本地 H5 仪表盘**。

```bash
# 启动本地可视化控制台服务
python scripts/run_dashboard.py
```
*启动后，在浏览器中打开：👉 **[http://127.0.0.1:8080/](http://127.0.0.1:8080/)***

### 🌟 仪表盘亮点功能：
- **全参数交互表单**：在页面中直接编辑项目名、大模型、分辨率、文案选题、切入角度、打标参数等。
- **6级实况步进器**：在运行期间，步进器（图片分拣 $\rightarrow$ 文案创作 $\rightarrow$ 画面对齐 $\rightarrow$ 海报生成 $\rightarrow$ 字幕合成 $\rightarrow$ MP4压缩）会根据控制台日志实时闪烁脉动、点亮并打勾！
- **复古终端模拟器**：支持彩色语法高亮日志，自动跟随向下滚动，科技感满满。
- **影院级视频播放**：支持流式分块寻址播放器，在网页上直接秒级预览并拖拽播放生成的无损 `.mp4` 视频。
- **2K 海报无损放大**：以瀑布流格栅列出所有 Playwright 截图，鼠标悬停带有动态反馈，点击支持**全屏高 DPI 无损灯箱放大**，完美查看车漆、轮毂细节。
- **报表一键下载**：彩色磁吸卡片，一键下载 Tagger 报表、打标 CSV 库、打标 JSON 和 Canva 映射表。

---

## ⚙️ 3. 一键命令行主控管道 (Master Pipeline - 适合高级创作者)

如果你偏爱使用命令行进行批量生产，可直接调用主控管道脚本 `scripts/run_pipeline.py`。该脚本自动穿接了 Stage 1（打标归档）和 Stage 2（文案与视频生成）。

### 示例 A：全功能一键运行（使用 Vision 视觉打标 + 2K 超清分辨率）
```bash
python scripts/run_pipeline.py \
  --name bmw_i3 \
  --brand BMW \
  --model i3 \
  --series "Neue Klasse" \
  --topic "BMW Neue Klasse i3" \
  --angle "宝马终于开始真正做电动车了" \
  --vision \
  --scale-factor 2
```

### 示例 B：极速一键运行（使用高速内置关键字打标，不拉起视觉模型）
```bash
python scripts/run_pipeline.py \
  --name bmw_i3 \
  --brand BMW \
  --model i3 \
  --series "Neue Klasse" \
  --topic "BMW Neue Klasse i3" \
  --angle "宝马终于开始真正做电动车了"
```

### 🔑 核心命令行参数指南：
- `--name`：项目唯一标识符，将决定输出文件和目录的名称。
- `--vision`：开启此参数，打标将调用本地 Ollama 多模态视觉大模型对图片进行精准分类；**如果不开启，则自动采用高精确率的本地关键字和图片高宽比算法进行毫秒级分类打标**。
- `--scale-factor`：**视网膜超清渲染系数**：
  - `2` (默认)：**Retina 2K 超清 ($2160 \times 2880$)**，文案边缘矢量级细腻，车身细节和质感拉满。
  - `3`：**4K 极致画质 ($3240 \times 4320$)**，发烧级清晰度。
  - `1`：**标准预览 ($1080 \times 1440$)**，极速渲染草稿。
- `--provider` / `--llm-model`：分别指定大模型驱动源（`ollama` / `openai`）及具体模型名称。如果不传，会自动读取 centralized 配置。
- `--skip-tagging`：跳过 Stage 1 打标整理，直接从 library 已有资产生成文案和视频。
- `--skip-generation`：只进行 Stage 1 资产分类与整理，暂不进行内容创作和视频合成。
- `--content <JSON路径>`：直接传入写好的文案 JSON 路径，跳过 LLM 创作等待，直接开始匹配出片。

---

## 📁 4. 统一大模型配置管理 (Unified Config)

我们实现了**模型参数的单一配置源管理**。你不需在代码和各种脚本里修改大模型名称，所有的全局默认模型均在 [config/settings.json](file:///Users/chengsc/auto_studio/config/settings.json) 中统一定义：

```json
{
  "default_model_openai": "gpt-4.1-mini",
  "default_model_ollama": "qwen2.5vl",
  "default_model_vision": "qwen2.5vl"
}
```
*在任何脚本或 H5 控制台中选择“默认模型”，系统都会自动解析并拉取此处的模型名称，实现“一处修改，处处生效”。*

---

## 📡 5. 辅助与监控功能

### 工信部自动监控
系统提供新车公告页面增量自动爬虫，支持根据你定义的关键词筛选新车，输出增量报告：
```bash
python scripts/monitor_miit.py
```
- **配置与关键词修改**：在 [config/settings.json](file:///Users/chengsc/auto_studio/config/settings.json) 中的 `"miit"` 字典下进行修改。
- **深度说明**：请参阅 [docs/MIIT_MONITOR.md](file:///Users/chengsc/auto_studio/docs/MIIT_MONITOR.md)。

### 素材合规原则
在收集官方图片和自媒体宣发时，请严格遵守版权合规指南，确保素材来源安全合规。
- **合规说明**：请参阅 [docs/LEGAL_ASSETS.md](file:///Users/chengsc/auto_studio/docs/LEGAL_ASSETS.md)。

---

## 📂 6. 核心产出物路径说明
- **整理好的规范素材库**：`assets/library/<brand>/<model>/`
- **打标资产报表 (Stage 1)**：`outputs/reports/<项目名>_assets_report.md` / `.csv` / `.json`
- **视觉文案 JSON (Stage 2)**：`outputs/content/<项目名>.json`
- **超清 Retina 2K 海报分片**：`outputs/images/<项目名>/`
- **超清 2K 压制视频与字幕**：`outputs/video/<项目名>.mp4` / `.srt`
- **Canva 映射配表**：`outputs/content/<项目名>_canva.csv`
