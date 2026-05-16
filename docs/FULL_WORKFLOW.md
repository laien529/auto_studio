# 完整工作流

## A. 监控

```bash
python scripts/monitor_miit.py
```

如果报告里出现新公告，人工看一眼标题，确定是否值得做选题。

## B. 生成内容

OpenAI：

```bash
python scripts/run_autopilot_openai.py
```

Ollama：

```bash
python scripts/run_autopilot_ollama.py
```

## C. 图片匹配

已在 run_autopilot 中自动执行。

## D. 自动出图

已在 run_autopilot 中自动执行。

## E. 视频

如果安装 ffmpeg，会自动输出 MP4。
如果没安装，也会输出 SRT，可在剪映使用。

## F. 发布

小红书：
直接发 outputs/images/项目名 下的9张图。

抖音：
发 outputs/video/项目名.mp4。

