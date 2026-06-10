---
name: 01-extract-storyboard
description: 从物理切分的镜头视频片段中提取关键帧，并使用视觉大模型分析生成原始分镜脚本数据表。
---

# 01 提取原视频分镜表 (Extract Storyboard)

## 概述 (Overview)
本技能用于分析 `output_scenes/` 目录下的所有 MP4 视频片段。它会提取各个镜头的时长、调用 FFmpeg 截图关键帧，最后请求视觉大模型识别景别、运镜和画面视觉描述，生成统一的 `storyboard.csv` 和 `storyboard.md`。

## 适用场景 (When to Use)
当您已经物理切分好原视频，想要提取并生成画面的结构化分镜数据时使用。

## 执行步骤 (Instructions)
在工作区根目录下执行：
```bash
python scripts/generate_storyboard.py --scenes-dir "output/scenes" --output-dir "output"
```

## 校验指标 (Verification)
1. 确认 `output/keyframes/` 目录下生成了关键帧 JPG 图片。
2. 确认 `output/storyboard.csv` 和 `output/storyboard.md` 包含原始镜头数据且内容完整。
