# -*- coding: utf-8 -*-
"""
脚本名称: evaluate_storylines.py
描述: 
    读取 `output/storyline_ideas.md` 中生成的 3 个脑暴故事大纲，
    调用大语言模型（LLM）API 进行多维度比对与评分评估。
    自动选择最优方案，将评估报告保存至 `output/evaluation_report.md`，
    并自动运行后续的 `generate_new_script.py` 与 `generate_video_prompts.py` 完成重绘工作流。
"""
import os
import sys
import json
import csv
import subprocess
import argparse

# 动态添加项目根目录到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import DEFAULT_OUTPUT_DIR, DEFAULT_STORYBOARD_CSV
from core.llm_client import call_t8star_llm
from core.utils import clean_json_response, get_logger

logger = get_logger("evaluate_storylines")

def main():
    parser = argparse.ArgumentParser(description="自动评估 3 个创意故事线并执行最优方案")
    parser.add_argument("--api-key", help="t8star API Key")
    parser.add_argument("--model", default="gpt-5.4-mini-2026-03-17", help="调用的模型名称")
    parser.add_argument("--base-url", default="https://ai.t8star.org/v1", help="API 的 baseurl 路径")
    parser.add_argument("--csv-input", default=DEFAULT_STORYBOARD_CSV, help="原分镜 CSV 路径")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="输出目录")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("T8STAR_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("缺少 API Key，请在根目录 .env 文件中配置 T8STAR_API_KEY。")
        sys.exit(1)

    output_dir = os.path.abspath(args.output_dir)
    storyline_md_path = os.path.join(output_dir, "storyline_ideas.md")
    csv_path = os.path.abspath(args.csv_input)

    # 1. 检查输入文件
    if not os.path.exists(storyline_md_path):
        logger.error(f"未找到故事大纲文件: {storyline_md_path}，请先运行 generate_creative_storylines.py")
        sys.exit(1)
        
    if not os.path.exists(csv_path):
        logger.error(f"未找到原分镜 CSV 文件: {csv_path}，无法为评估提供原分镜上下文参考")
        sys.exit(1)

    # 2. 读取脑暴的故事线
    logger.info("正在加载 3 种故事线方案...")
    with open(storyline_md_path, "r", encoding="utf-8") as f:
        storyline_content = f.read()

    # 3. 读取原分镜数据做为上下文参考
    scenes_summary = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            orig_content = row.get("原画面内容", row.get("画面内容", ""))
            scenes_summary.append({
                "镜号": row["镜号"],
                "景别": row["景别"],
                "运镜": row.get("运动镜头", row.get("运镜", "")),
                "时长": row.get("时长(秒)", row.get("时长", "")),
                "原内容": orig_content[:40] + "..." if len(orig_content) > 40 else orig_content
            })
    scenes_json_str = json.dumps(scenes_summary, ensure_ascii=False, indent=2)

    # 4. 构建评估提示词
    logger.info("正在调用 API 对 3 种方案进行全方位评估...")
    
    prompt = f"""你是一个专业的影视制片人和视觉导演。
下面是脑暴出的 3 种新故事线大纲（来自 `storyline_ideas.md`）：
{storyline_content}

同时，我们参考的原视频分镜数据（包括各镜头的景别、运镜和原内容摘要）如下:
{scenes_json_str}

请根据以下维度评估这 3 个故事大纲，并挑选出最适合使用 AI 视频生成工具（如 Luma, Runway Gen-3 等）进行重绘的最优方案：
1. **视听镜头适配度**：新故事中的动作、情景是否完美契合原视频 38 个镜头的物理景别（如特写、近景、中景、全景）和运镜（如固定、推、拉、平移）。例如，原片是特写双手，新故事在此处也应该有合理的双手或微观动作；原片是全景，新故事也应处于大场景中。
2. **AI 生成可行性**：新故事的场景、人物形象在 AI 视频生成中是否易于保持视觉一致性，背景是否容易渲染，是否能生成连贯流畅的视频片段。
3. **叙事张力与情感深度**：故事大纲本身的情感起伏是否动人，冲突是否合理，解决执念/心结的转折是否自然。

请输出详细的评估分析报告，包含对 3 个方案的逐一打分评分（满分10分）、优缺点分析，以及最终选择理由。同时，针对选中的获胜方案，生成 3-4 个核心视觉资产（如主要角色人像、次要角色人像、核心场景/风格图）的生图提示词（Text-to-Image Prompts，包括中文和适合 Midjourney / Flux 的英文提示词，且对于人物角色资产，必须同时包含单人肖像提示词与角色三视图提示词）。

【生图提示词生成规范 (基于 GPTImage2 和 NanoBanana 融合规范，完全排除任何项目内本地私有标签)】：
1. 单人肖像及场景风格提示词结构（混合公式）：
   `[Type of Image / FORM] of [FOCUS / Character] [Action / FACTS] in [PLACE / Setting], shot from [Camera angle]. The style is [Style Reference] with [Lighting/Mood], [High-resolution details], [FORBIDDEN]`
   例如：`Cinematic close-up shot of a 40-year-old Asian woman, standing on an old small-town street during an overcast evening. She is wearing a beige trench coat, with short black hair tied in a low ponytail. Her shoulders are slightly slouched, her lips are closed in a straight line, and she has subtle fine lines under her eyes, looking quietly and directly at the camera with a neutral expression. Realistic documentary photograph style, 35mm film, soft natural ambient lighting, low contrast, high-fidelity skin pores and textures, for consistent character preservation. No watermarks, no signatures, no text, no cartoon style, no blurry face.`
2. 仅针对人物角色资产，增加“角色多视角三视图（Character Turnaround Sheet）”提示词，公式为：
   `Character turnaround sheet, multiple angles showing front view, side view, and back view of [FOCUS/角色主体], [FACTS/衣着/物理细节], clean solid background. The style is [FORM/媒介/风格] with [Lighting/光影氛围], [特征一致性描述，使用 consistent character/preserve identity 锁定面部] --ar 16:9 --no [FORBIDDEN/排除词]`
   例如：`Character turnaround sheet, multiple angles showing front view, side view, and back view of a 40-year-old Asian woman with short black hair tied in a low ponytail, wearing a beige trench coat, clean solid light grey background. Realistic cinematic character design style, 35mm film, even flat lighting, for consistent character preservation and precise clothing detail. --ar 16:9 --no watermarks, signatures, grid lines, text`
3. 纯物理事实描述铁律：杜绝任何文学修辞与主观情感词汇（如“气质疲惫但克制”、“带记忆感”、“带岁月智慧”、“神情通透”），必须转译为摄像机可拍到的微表情、服饰材质、灯光、物理道具或具体摆设。
4. 排除水印和无关文本，单人画幅比例人物设为 --ar 3:2（三视图设为 --ar 16:9），场景设为 --ar 16:9。

请【严格】以双花括号包裹的 JSON 格式返回，保证最外层为 JSON 结构：
{{
  "评估分析报告": "Markdown 格式的详细分析报告，包含各个维度的打分（满分10分）、优缺点分析以及最终选择理由。",
  "获胜方案索引": 1, 
  "获胜方案标题": "选中的方案标题",
  "获胜方案大纲": "选中的方案大纲文字描述",
  "参考角色": "用于 --character 参数的最佳简洁角色名称，例如 '年轻女修船匠'",
  "新场景": "用于 --scene 参数的最佳简洁场景描述，例如 '旧海边码头与船厂'",
  "新画面风格": "用于 --visual-style 参数的最佳画面风格设定，例如 '海滨写实电影风格，带有一丝咸湿海风与怀旧暖色调'",
  "资产列表": [
    {{
      "资产名称": "资产角色名称或场景名称，例如 '年轻女修船匠林艾' 或 '废弃的旧码头'",
      "资产类型": "资产分类，可选值为 'character'（角色人物）或 'scene'（场景风格）",
      "英文短ID": "用于文件命名的简短英文标识（小写英文字母及下划线，例如 'lin_ai' 或 'old_pier'）",
      "资产描述": "描述该资产在画面中的主要特征与衣着/外观设定",
      "中文生成提示词": "中文肖像提示词或场景风格提示词（不含三视图）",
      "英文生成提示词": "英文肖像提示词或场景风格提示词（不含三视图）",
      "中文三视图提示词": "（仅当资产类型为 'character' 时提供）用于生成该角色正、侧、背面三视图的中文提示词，如果是 scene 则返回空字符串",
      "英文三视图提示词": "（仅当资产类型为 'character' 时提供）用于生成该角色正、侧、背面三视图的英文提示词，如果是 scene 则返回空字符串"
    }}
  ]
}}
"""

    response_text = call_t8star_llm(api_key, args.base_url, args.model, prompt, temperature=0.3)
    if not response_text:
        logger.error("API 评估请求未返回结果。")
        sys.exit(1)

    cleaned_json = clean_json_response(response_text)
    
    try:
        eval_data = json.loads(cleaned_json)
        report = eval_data.get("评估分析报告", "")
        winning_idx = eval_data.get("获胜方案索引", 1)
        winning_title = eval_data.get("获胜方案标题", "")
        winning_desc = eval_data.get("获胜方案大纲", "")
        char_val = eval_data.get("参考角色", "主角")
        scene_val = eval_data.get("新场景", "自适应场景")
        style_val = eval_data.get("新画面风格", "写实电影风格")
        assets = eval_data.get("资产列表", [])
        
        # 5. 保存评估报告为 Markdown
        report_path = os.path.join(output_dir, "evaluation_report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# 3种故事大纲智能评估报告\n\n")
            f.write(f"本评估报告由 AI 自动生成，旨在为视频重绘寻找与原片视听节奏契合度最高、生成效果最好的故事大纲。\n\n")
            f.write(f"## 🏆 评估结论：方案 {winning_idx} —— 《{winning_title}》 胜出！\n\n")
            f.write(f"### 方案基本参数：\n")
            f.write(f"- **大纲描述**：{winning_desc}\n")
            f.write(f"- **参考角色**：{char_val}\n")
            f.write(f"- **新场景**：{scene_val}\n")
            f.write(f"- **新画面风格**：{style_val}\n\n")
            f.write(f"---\n\n")
            
            # 写入资产图提示词到主评估报告
            if assets:
                f.write(f"## 🎨 方案核心视觉资产提示词 (Image Prompts)\n\n")
                f.write(f"在运行视频重绘前，请使用以下提示词在 AI 绘图工具（如 Midjourney / Flux / SD）中生成核心资产图片，作为重绘的 Image Prompt 参考，以保证全片人像与画风的一致性：\n\n")
                for asset in assets:
                    name = asset.get("资产名称", "未命名资产")
                    desc = asset.get("资产描述", "")
                    prompt_cn = asset.get("中文生成提示词", "")
                    prompt_en = asset.get("英文生成提示词", "")
                    f.write(f"### 📍 资产：{name}\n")
                    f.write(f"- **外观描述**：{desc}\n")
                    
                    if asset.get("资产类型") == "character" and asset.get("英文三视图提示词"):
                        f.write(f"- **A. 角色单人肖像提示词 (Portrait Prompt - 3:2)**：\n")
                        f.write(f"  * **中文 Prompt**：\n    ```\n    {prompt_cn}\n    ```\n")
                        f.write(f"  * **英文 Prompt**：\n    ```\n    {prompt_en}\n    ```\n")
                        
                        f.write(f"- **B. 角色多视角三视图提示词 (Turnaround Sheet Prompt - 16:9)**：\n")
                        f.write(f"  * **中文 Prompt**：\n    ```\n    {asset.get('中文三视图提示词')}\n    ```\n")
                        f.write(f"  * **英文 Prompt**：\n    ```\n    {asset.get('英文三视图提示词')}\n    ```\n")
                    else:
                        f.write(f"- **中文生图提示词**：\n  ```\n  {prompt_cn}\n  ```\n")
                        f.write(f"- **英文生图提示词 (推荐 Midjourney/Flux)**：\n  ```\n  {prompt_en}\n  ```\n")
                    f.write("\n")
                f.write(f"---\n\n")
                
            f.write(f"## 详细对比评估内容\n\n")
            f.write(report)
            f.write(f"\n\n---\n*评估报告生成时间: 2026-06-11*")

        logger.info(f"评估报告生成成功，已保存至: {report_path}")
        
        # 同时生成一份独立的资产提示词文档，方便用户快速复制
        if assets:
            asset_md_path = os.path.join(output_dir, "asset_prompts.md")
            with open(asset_md_path, "w", encoding="utf-8") as f:
                f.write(f"# 《{winning_title}》 —— 核心视觉资产生图提示词\n\n")
                f.write(f"本文件包含该重绘方案所需的所有核心人像与场景风格参考图生成提示词，完全遵循 GPTImage2 与 NanoBanana 融合规范。\n\n")
                for asset in assets:
                    name = asset.get("资产名称", "未命名资产")
                    desc = asset.get("资产描述", "")
                    prompt_cn = asset.get("中文生成提示词", "")
                    prompt_en = asset.get("英文生成提示词", "")
                    f.write(f"## 📍 资产：{name}\n")
                    f.write(f"* **外观特征**：{desc}\n")
                    
                    if asset.get("资产类型") == "character" and asset.get("英文三视图提示词"):
                        f.write(f"### A. 角色单人肖像提示词 (Portrait Prompt - 3:2)\n")
                        f.write(f"* **中文 Prompt**：`{prompt_cn}`\n")
                        f.write(f"* **英文 Prompt**：`{prompt_en}`\n\n")
                        
                        f.write(f"### B. 角色多视角三视图提示词 (Turnaround Sheet Prompt - 16:9)\n")
                        f.write(f"* **中文 Prompt**：`{asset.get('中文三视图提示词')}`\n")
                        f.write(f"* **英文 Prompt**：`{asset.get('英文三视图提示词')}`\n\n")
                    else:
                        f.write(f"* **中文 Prompt**：`{prompt_cn}`\n")
                        f.write(f"* **英文 Prompt**：`{prompt_en}`\n\n")
                    f.write(f"---\n\n")
            logger.info(f"核心视觉资产生图提示词文档已成功保存至: {asset_md_path}")
            
            # 构造并生成资产元数据
            metadata = {
                "characters": {},
                "scenes": {}
            }
            for asset in assets:
                name = asset.get("资产名称", "未命名资产")
                asset_type = asset.get("资产类型", "character")
                short_id = asset.get("英文短ID", "asset").lower().strip().replace(" ", "_")
                
                # 过滤文件名中非字母数字和下划线的字符
                import re
                short_id = re.sub(r'[^a-z0-9_]', '', short_id)
                if not short_id:
                    short_id = "asset"
                
                path = f"assets/{short_id}_ref.png"
                
                # 优化资产分类容错逻辑：支持多种拼写以及中文判断，增强特定地缘/环境关键词识别
                asset_type_clean = str(asset_type).strip().lower()
                is_scene = False
                if asset_type_clean in ["scene", "scenes", "场景", "场景风格"]:
                    is_scene = True
                else:
                    # 地理、建筑、公共设施环境类常见词判定为场景
                    scene_keywords = [
                        "场景", "背景", "内部", "外观", "环境", "空间",
                        "站台", "候车亭", "长椅", "公园", "游乐场", "码头", "广场", 
                        "路", "街", "校园", "工作室", "房间", "厂房", "亭", "台"
                    ]
                    if any(kw in name for kw in scene_keywords):
                        is_scene = True
                
                if is_scene:
                    metadata["scenes"][name] = path
                else:
                    metadata["characters"][name] = path
            
            metadata_path = os.path.join(output_dir, "assets_metadata.json")
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            logger.info(f"已生成资产匹配元数据文件: {metadata_path}")
            
        logger.info(f"评估结果为 方案 {winning_idx}《{winning_title}》 最为适合。")
        
        # 6. 自动化执行最优方案
        logger.info(f"【自动化执行】启动步骤 1/2: 重新改写剧本 (generate_new_script.py)...")
        # 构造执行命令行参数
        # 注意对字符串参数进行包装，防止命令行特殊字符报错
        cmd_rewrite = [
            sys.executable,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_new_script.py"),
            "--api-key", api_key,
            "--model", args.model,
            "--base-url", args.base_url,
            "--csv-input", csv_path,
            "--output-dir", output_dir,
            "--storyline-title", winning_title,
            "--storyline", winning_desc,
            "--character", char_val,
            "--scene", scene_val,
            "--visual-style", style_val
        ]
        
        console_encoding = sys.stdout.encoding or "utf-8"
        logger.info(f"正在运行: {' '.join(cmd_rewrite[:10])} ...")
        res_rewrite = subprocess.run(cmd_rewrite, capture_output=True, text=True, encoding=console_encoding, errors="replace")
        if res_rewrite.returncode != 0:
            logger.error(f"剧本改写脚本运行失败！错误日志：\n{res_rewrite.stderr}")
            sys.exit(1)
        logger.info("剧本改写脚本成功运行完成！")
        
        logger.info(f"【自动化执行】启动步骤 2/2: 生成视频重绘提示词 (generate_video_prompts.py)...")
        cmd_prompts = [
            sys.executable,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_video_prompts.py"),
            "--csv-input", csv_path,
            "--output-dir", output_dir
        ]
        
        logger.info(f"正在运行: {' '.join(cmd_prompts)} ...")
        res_prompts = subprocess.run(cmd_prompts, capture_output=True, text=True, encoding=console_encoding, errors="replace")
        if res_prompts.returncode != 0:
            logger.error(f"重绘提示词生成脚本运行失败！错误日志：\n{res_prompts.stderr}")
            sys.exit(1)
        logger.info("重绘提示词生成脚本成功运行完成！")
        
        logger.info("[Success] 自动化流程全部成功执行完毕！故事分镜已被重构。")
        
    except Exception as e:
        logger.error(f"解析大模型评估 JSON 失败: {e}。原始返回文本：\n{response_text}")
        sys.exit(1)

if __name__ == "__main__":
    main()
