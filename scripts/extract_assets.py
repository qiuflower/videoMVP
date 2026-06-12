# -*- coding: utf-8 -*-
"""
脚本名称: extract_assets.py
描述: 
    读取生成后的 storyboard.csv，解析并去重其中出现的所有“参考角色”与“新场景”。
    调用大语言模型（LLM）API 对提取出的物理角色与场景进行分类归纳，并生成
    符合 GPTImage2 和 NanoBanana 融合规范的核心视觉资产提示词（肖像、三视图及场景图）。
    最后导出 assets_metadata.json 以及独立的 asset_prompts.md。
"""
import os
import sys
import csv
import json
import argparse
import re

# 动态添加项目根目录到 sys.path，支持在任意目录下运行该脚本
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import DEFAULT_OUTPUT_DIR, DEFAULT_STORYBOARD_CSV, DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_API_KEY
from core.llm_client import call_t8star_llm
from core.utils import clean_json_response, get_logger

logger = get_logger("extract_assets")

def main():
    parser = argparse.ArgumentParser(description="根据改写后的剧本自动提取并生成视觉资产提示词")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="t8star API Key")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="调用的模型名称")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API 的 baseurl 路径")
    parser.add_argument("--csv-input", default=DEFAULT_STORYBOARD_CSV, help="主分镜 CSV 路径")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="输出目录")
    parser.add_argument("--storyline-title", default="", help="故事标题")
    parser.add_argument("--storyline", default="", help="故事大纲")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("T8STAR_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("缺少 API Key，请在根目录 .env 文件中配置 T8STAR_API_KEY。")
        sys.exit(1)

    csv_path = os.path.abspath(args.csv_input)
    if not os.path.exists(csv_path):
        logger.error(f"未找到分镜 CSV 文件: {csv_path}")
        sys.exit(1)

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # 1. 读取 CSV 中所有的参考角色与新场景
    raw_characters = set()
    raw_scenes = set()
    visual_styles = []

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            char_val = row.get("参考角色", "").strip()
            scene_val = row.get("新场景", "").strip()
            style_val = row.get("新画面风格", "").strip()

            if char_val and char_val not in ["无", "无人物", "自适应", "默认风格", "待生成"]:
                # 分割可能包含的多人物描述，如“主角与女儿”或“陈岚和陈教授”
                # 进行简单的字符分词，或者直接保留由LLM处理
                raw_characters.add(char_val)
            if scene_val and scene_val not in ["无", "自适应", "默认风格", "待生成"]:
                raw_scenes.add(scene_val)
            if style_val and style_val not in ["无", "默认风格"]:
                visual_styles.append(style_val)

    if not raw_characters and not raw_scenes:
        logger.warning("在 CSV 中未提取到有效的角色与场景信息。")
        sys.exit(0)

    # 获取最常出现的画面风格作为参考
    from collections import Counter
    visual_style = Counter(visual_styles).most_common(1)[0][0] if visual_styles else "写实电影风格"

    # 尝试从已有的 storyboard.md 中读取故事标题
    storyline_title = args.storyline_title
    if not storyline_title:
        md_path = os.path.join(output_dir, "storyboard.md")
        if os.path.exists(md_path):
            try:
                with open(md_path, "r", encoding="utf-8") as f_md:
                    first_line = f_md.readline().strip()
                    if first_line.startswith("#"):
                        title_part = first_line.replace("#", "").split("——")[0].strip()
                        if title_part:
                            storyline_title = title_part
            except Exception:
                pass
    if not storyline_title:
        storyline_title = "视频智能重绘故事"

    storyline_desc = args.storyline or "基于原片节奏重绘的故事短片"

    logger.info(f"开始提取核心视觉资产。去重后的原始角色列表: {list(raw_characters)}")
    logger.info(f"去重后的原始场景列表: {list(raw_scenes)}")

    # 2. 构建大模型提示词进行资产提取与描述扩写
    prompt = f"""你是一个顶级的视觉导演与 AI 生图提示词专家。
目前，我们已经根据原片分镜改写完成了新剧本，现在需要为该剧本中出现的人物和场景动态提取并生成视觉资产（Core Visual Assets）生图提示词。

【剧本基本信息】：
- 故事标题：《{storyline_title}》
- 故事大纲：{storyline_desc}
- 全局画面风格：{visual_style}

【从38镜剧本中提取出的原始参考角色列表】：
{chr(10).join(f"- {c}" for c in raw_characters)}

【从38镜剧本中提取出的原始新场景列表】：
{chr(10).join(f"- {s}" for s in raw_scenes)}

【任务要求】：
1. **分类、归纳并合并资产**：分析上述列表，确定故事里实际出现的独立【核心角色】（如将带有“主角”、“主角与女儿”、“女儿”的行提炼出“中年女性主角陈岚”与“小女儿林夏”两个独立人像资产，去掉无关的复合词，仅保留独立单人角色资产）和【核心场景】（如将各种厨房角落的描述归纳为“老宅厨房”）。
2. **生成生图提示词（遵循 GPTImage2 / NanoBanana 规范）**：
   - 物理事实描述铁律：**必须完全排除任何抽象、文学修辞或主观情感词汇**（如“神情通透”、“带岁月智慧”、“气质疲惫”等），必须将其翻译为可被摄像机拍摄到的物理事实（如微表情、皱纹、服装材质、道具、特定的光影）。
   - 水印与额外文本过滤：禁止包含 watermark, signature, text, cartoon 等。
   - 人物画幅比例设为 --ar 3:2，三视图与场景画幅比例设为 --ar 16:9。
   - 人物资产必须生成两种提示词：
     A. **单人肖像提示词 (Portrait Prompt)**：半身/近景电影肖像照，画幅比例 --ar 3:2。
     B. **角色多视角三视图提示词 (Character Turnaround Sheet)**：正面、侧面、背面三视图，纯浅灰背景，画幅比例 --ar 16:9，使用 consistent character/preserve identity。
   - 场景资产仅需生成一种：
     A. **场景风格提示词 (Scene Prompt)**：宽幅环境空镜，画幅比例 --ar 16:9。

请严格以 JSON 格式返回，保证最外层为 JSON 结构：
{{
  "资产列表": [
    {{
      "资产名称": "资产具体名称，如 '中年女性主角陈岚' 或 '老宅厨房'",
      "资产类型": "资产分类，可选值为 'character'（角色人物）或 'scene'（场景风格）",
      "英文短ID": "用于文件命名的简短英文标识（小写英文字母及下划线，例如 'chen_lan' 或 'old_kitchen'）",
      "资产描述": "描述该资产在画面中的主要特征与衣着/外观设定",
      "中文生成提示词": "中文肖像提示词或场景风格提示词（不含三视图）",
      "英文生成提示词": "英文肖像提示词或场景风格提示词（不含三视图）",
      "中文三视图提示词": "（仅当资产类型为 'character' 时提供）用于生成该角色正、侧、背面三视图的中文提示词，如果是 scene 则返回空字符串",
      "英文三视图提示词": "（仅当资产类型为 'character' 时提供）用于生成该角色正、侧、背面三视图的英文提示词，如果是 scene 则返回空字符串"
    }}
  ]
}}
"""

    logger.info("正在调用 API 提取并扩写视觉资产...")
    response_text = call_t8star_llm(api_key, args.base_url, args.model, prompt, temperature=0.3)
    if not response_text:
        logger.error("API 未返回资产提取结果。")
        sys.exit(1)

    cleaned_json = clean_json_response(response_text)
    
    try:
        data = json.loads(cleaned_json)
        assets = data.get("资产列表", [])
        if not assets:
            logger.warning("解析 JSON 成功，但未发现有效的“资产列表”数据。")
            sys.exit(0)

        # 3. 写入独立的资产提示词文档 asset_prompts.md
        asset_md_path = os.path.join(output_dir, "asset_prompts.md")
        with open(asset_md_path, "w", encoding="utf-8") as f:
            f.write(f"# 《{storyline_title}》 —— 核心视觉资产生图提示词\n\n")
            f.write("本文件包含从最终剧本中动态提取的角色人像与场景风格参考图生成提示词，遵循 GPTImage2 与 NanoBanana 融合规范。\n\n")
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
        logger.info(f"核心视觉资产生图提示词已保存至: {asset_md_path}")

        # 4. 生成元数据文件 assets_metadata.json
        metadata = {
            "characters": {},
            "scenes": {}
        }
        for asset in assets:
            name = asset.get("资产名称", "未命名资产")
            asset_type = asset.get("资产类型", "character")
            short_id = asset.get("英文短ID", "asset").lower().strip().replace(" ", "_")
            
            # 过滤文件名
            short_id = re.sub(r'[^a-z0-9_]', '', short_id)
            if not short_id:
                short_id = "asset"
            
            path = f"assets/{short_id}_ref.png"
            
            # 强化场景类型容错逻辑
            asset_type_clean = str(asset_type).strip().lower()
            is_scene = False
            if asset_type_clean in ["scene", "scenes", "场景", "场景风格"]:
                is_scene = True
            else:
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
        logger.info(f"已生成/更新资产元数据文件: {metadata_path}")

    except Exception as e:
        logger.error(f"解析资产提取 JSON 失败: {e}。原始返回文本:\n{response_text}")
        sys.exit(1)

if __name__ == "__main__":
    main()
