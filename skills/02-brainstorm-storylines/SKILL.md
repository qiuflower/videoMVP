---
name: 02-brainstorm-storylines
description: 读取视频分镜 CSV 数据，根据原镜头景别与时长节奏智能脑暴出 3 种新故事线大纲。
---

# 02 脑暴全新故事大纲 (Brainstorm Storylines)

## 概述 (Overview)
本技能用于分析已生成的 `storyboard.csv`，基于原视频的镜头时长和情绪节奏点，调用文本大模型脑暴并输出 3 个完全不同的、贴合镜头运动的角色故事线大纲。

## 适用场景 (When to Use)
在准备改写剧本前，需要对新故事题材与主角设定进行创意激发时使用。

## 执行步骤 (Instructions)
在工作区根目录下执行：
```bash
python scripts/generate_creative_storylines.py --csv-input "output/storyboard.csv" --output-dir "output"
```

## 校验指标 (Verification)
1. 确认在 `output/` 目录下生成了 `storyline_ideas.md` 脑暴推荐文档。
2. 打开文件，里面应包含 3 个备选故事线方案（包含标题、核心题材、角色对照及大纲描述）。
