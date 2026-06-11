---
name: 03-rewrite-script
description: 根据指定的新故事线大纲及原视频分镜节奏，调用大模型重写每镜画面描述、台词及音效。
---

# 03 匹配节奏改写分镜剧本 (Rewrite Script)

## 概述 (Overview)
本技能根据用户传入的故事大纲和标题，调用文本大模型逐批改写 `storyboard.csv` 中的画面内容、台词与音效。通过设定新人物、新场景、新焦段、镜头方位及画面风格参数，仅针对这 5 个维度进行替换和重写，同时 100% 保持原片景别、运镜、时长和动作逻辑。

## 适用场景 (When to Use)
在脑暴出新故事大纲后，或者对原片进行仅替换人物/场景/风格的视频重绘时使用。

## 执行步骤 (Instructions)
在工作区根目录下执行（可根据需要传入人物、场景、焦段、镜头方位与画面风格参数）：
```bash
python scripts/generate_new_script.py --csv-input "output/storyboard.csv" --output-dir "output" --storyline "<您选中的故事大纲描述>" --storyline-title "<您的剧本标题>" --character "<替换后人物>" --scene "<替换后场景>" --focal-length "<推荐焦段>" --camera-direction "<镜头方位>" --visual-style "<画面风格>"
```

## 校验指标 (Verification)
1. 确认 `output/storyboard.csv` 中新增了 `新场景`、`新焦段`、`新镜头方位`、`新画面风格`、`参考角色`、`新台词/旁白` 等列。
2. 确认 `output/storyboard.md` 渲染成功，展示包含这 5 要素的新剧本。
