---
name: 04-generate-video-prompts
description: 根据重写后的新分镜剧本细节，自动合成带有参考角色与运镜约束的视频重绘提示词列。
---

# 04 自动合成视频重绘提示词 (Generate Video Prompts)

## 概述 (Overview)
本技能读取改写后的 `storyboard.csv`，并根据结构模板将景别、运动镜头、新画面内容、台词、时长及参考人像角色融合，生成用于 AI 视频生成引擎的视频重绘提示词，并追加导出。

## 适用场景 (When to Use)
在剧本改写完成后，为方便将提示词批量拷贝导入 AI 视频重绘引擎时使用。

## 执行步骤 (Instructions)
在工作区根目录下执行：
```bash
python scripts/generate_video_prompts.py --csv-input "output/storyboard.csv" --output-dir "output"
```

## 校验指标 (Verification)
1. 确认 `output/storyboard.csv` 和 `output/storyboard.md` 中追加了 `"视频重绘提示词"` 列。
2. 提示词内容应符合标准格式模板。
