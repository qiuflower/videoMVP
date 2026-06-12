# videoMVP

## 🎬 智能视频重绘与分镜重塑工作流 (Sequence Flow)

以下为工作流从**物理镜头分割**、**多模态视觉识别**、**创意大纲脑暴与智能评估**，到**剧本改写**、**资产语义绑定**、**解耦提示词编译**以及最后的**多模态 Cref/Sref 生图**的完整 UML 时序流程：

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户 (User)
    participant Client as 客户端/主控脚本 (main.py)
    participant Tool as FFmpeg/PySceneDetect
    participant TextAPI as LLM 文本 API (t8star-llm)
    participant VisionAPI as LLM 视觉 API (t8star-vision)
    participant ImgAPI as 生图 API (gpt-image-2)

    %% Step 1: 物理分切
    Note over Client, Tool: Step 1: 物理分切 (split_video.py)
    User->>Client: 执行一键启动流水线
    Client->>Tool: 调用 PySceneDetect / FFmpeg 物理分割视频
    Tool-->>Client: 返回各个镜头的 .mp4 视频片段

    %% Step 2: 视觉提取与分镜识别
    Note over Client, VisionAPI: Step 2: 视觉提取与分镜识别 (generate_storyboard.py)
    Client->>Tool: 提取每个镜头的 1-3 张关键帧图像并转为 Base64
    Client->>VisionAPI: 发送 vision_prompt + 关键帧 Base64 数组 (JSON 模式)
    VisionAPI-->>Client: 返回镜头景别、运镜、画面内容、台词的 JSON 数据
    Client->>Client: 保存至原始分镜数据表 storyboard.csv

    %% Step 3: 创意故事线大纲脑暴
    Note over Client, TextAPI: Step 3: 创意故事线大纲脑暴 (generate_creative_storylines.py)
    Client->>TextAPI: 注入压缩后的原视频分镜节奏数据，脑暴新故事
    TextAPI-->>Client: 返回 3 套题材迥异的故事大纲 JSON 数据
    Client->>Client: 保存至大纲文件 storyline_ideas.md

    %% Step 4: 故事线智能评估
    Note over Client, TextAPI: Step 4: 故事线智能评估与自动方案调度 (evaluate_storylines.py)
    Client->>TextAPI: 评估这 3 套故事线大纲与原片节奏的契合度，选择获胜方案
    TextAPI-->>Client: 返回获胜方案索引及核心人物/场景/风格参数
    Client->>Client: 保存评估报告至 evaluation_report.md 并自动调度子工作流

    %% Step 5: 剧本重构与改写
    Note over Client, TextAPI: Step 5: 剧本逐批改写与画面重构 (generate_new_script.py)
    Client->>TextAPI: 每 6 镜分批发送改写请求 (原镜头描述 + 新设定)
    TextAPI-->>Client: 返回改写后的剧本分镜 JSON 数组 (保持原规格)
    Client->>Client: 更新至主数据表 storyboard.csv 并生成初始剧本

    %% Step 6: 核心资产提取
    Note over Client, TextAPI: Step 6: 核心资产提取与扩写 (extract_assets.py)
    Client->>TextAPI: 发送去重后的角色和场景名称列表
    TextAPI-->>Client: 返回各资产详细肖像/环境中文及英文生图 Prompt JSON
    Client->>Client: 写入 assets_metadata.json 与 asset_prompts.md

    %% Step 7: 智能资产语义绑定
    Note over Client, TextAPI: Step 7: 智能资产语义绑定 (bind_assets.py)
    Client->>TextAPI: 发送剧本分镜列表 + 可用资产列表
    TextAPI-->>Client: 返回每个分镜映射关联的角色与场景资产 JSON
    Client->>Client: 写入绑定映射结果文件 asset_bindings.json

    %% Step 8: 解耦提示词编译
    Note over Client, TextAPI: Step 8: 解耦提示词编译 (generate_video_prompts.py)
    Client->>TextAPI: 发送剧本、资产 and 绑定，调用 decoupled_prompts_prompt.txt 模板
    TextAPI-->>Client: 返回首帧提示词、尾帧提示词、视频重绘提示词 JSON
    Client->>Client: 合并写入 storyboard.csv 并生成最终主分镜脚本 storyboard.md

    %% Step 9: 批量生图与渲染
    Note over Client, ImgAPI: Step 9: 批量生图与渲染 (generate_images.py)
    User->>Client: 启动批量生图脚本 (generate_images.py)
    Client->>ImgAPI: 发送资产英文 Prompt 生成核心参考图
    ImgAPI-->>Client: 返回图像下载链接，存至 assets/*_ref.png
    Client->>ImgAPI: 多模态双图/三图注入 (角色 Cref + 场景 Sref + 姿态关键帧 Base64)
    ImgAPI-->>Client: 返回新首帧/尾帧生图 URL 链接并下载至本地
    Client->>User: 激活 storyboard.md 中的本地分镜预览，完成智能重绘
```

---

## 📖 核心使用指南

### 第一步：一键运行流水线生成剧本
在项目根目录下打开终端，运行：
```bash
python main.py
```
* **效果**：脚本会自动化执行视频切割、帧提取、故事大纲脑暴与评估，并完成剧本的改写及提示词编译，在 `output/` 中输出 `storyboard.csv`、`storyboard.md` 等数据。
* **说明**：此步骤不调用生图接口，速度快且不产生高昂的图像 API 费用，以便您先校验剧本文案。

### 第二步：准备视觉资产参考图 (人脸锁 / Cref)
根据流水线在 `output/asset_prompts.md` 中为您规划的角色：
* **选择 A：上传自己准备的高一致性人脸**：
  您可以把您自定义好的参考图放入 `assets/` 目录中，并命名为对应名称（例如：`lin_he_ref.png`、`zhou_bo_ref.png`）。
* **选择 B：让大模型代为生成基础参考图**：
  如果不上传任何图，生图脚本会在下一步自动调用 API 帮您生出默认的角色参考图。

### 第三步：批量生成所有镜头的分镜图
在终端执行批量图生图下载脚本：
```bash
python scripts/generate_images.py
```
* **效果**：脚本将读取剧本，把所有的**人脸资产图**（多角色可同时输入）与原片提取的**构图姿态关键帧**全部在内存中优化压缩，并以多模态 payload 传入大模型生图，自动将图片保存至 `assets/`。
* **结果**：全部运行完成后，用支持预览的 Markdown 查看器（如 VS Code 预览）打开 `output/storyboard.md`，即可浏览已激活且对齐的高精度重绘分镜。
