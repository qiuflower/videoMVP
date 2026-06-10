---
name: 03-rewrite-script
description: 根据指定的新故事线大纲及原视频分镜节奏，调用大模型重写每镜画面描述、台词及音效。
---

# 03 匹配节奏改写分镜剧本 (Rewrite Script)

## 概述 (Overview)
本技能根据用户传入的故事大纲和标题，调用文本大模型逐批改写 `storyboard.csv` 中的画面内容、台词与音效。重写后的画面会服务于新大纲，但物理参数（景别、运镜、时长）与原片 100% 保持一致，从而适配原片节奏。

## 适用场景 (When to Use)
在脑暴出新故事大纲后，需要详细改写每一镜头的剧本台词、新画面动作以及新音乐/音效时使用。

## 执行步骤 (Instructions)
在工作区根目录下执行（将 `<大纲>` 与 `<标题>` 替换为实际文字）：
```bash
python scripts/generate_new_script.py --csv-input "output/storyboard.csv" --output-dir "output" --storyline "<您选中的故事大纲描述>" --storyline-title "<您的剧本标题>"
```

## 校验指标 (Verification)
1. 确认 `output/storyboard.csv` 中被写入了新剧本列（“新画面内容”、“参考角色”、“新台词/旁白”、“新音效/音乐”）。
2. 确认 `output/storyboard.md` 渲染成功，展示新旧对比。
