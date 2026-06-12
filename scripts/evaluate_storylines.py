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

from core.config import DEFAULT_OUTPUT_DIR, DEFAULT_STORYBOARD_CSV, DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_API_KEY
from core.llm_client import call_t8star_llm
from core.utils import clean_json_response, get_logger

logger = get_logger("evaluate_storylines")

def main():
    parser = argparse.ArgumentParser(description="自动评估 3 个创意故事线并执行最优方案")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="t8star API Key")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="调用的模型名称")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API 的 baseurl 路径")
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

请输出详细的评估分析报告，包含对 3 个方案的逐一打分评分（满分10分）、优缺点分析，以及最终选择理由。

请【严格】以双花括号包裹的 JSON 格式返回，保证最外层为 JSON 结构：
{{
  "评估分析报告": "Markdown 格式的详细分析报告，包含各个维度的打分（满分10分）、优缺点分析以及最终选择理由。",
  "获胜方案索引": 1, 
  "获胜方案标题": "选中的方案标题",
  "获胜方案大纲": "选中的方案大纲文字描述",
  "参考角色": "用于 --character 参数的最佳简洁角色名称，例如 '年轻女修船匠'",
  "新场景": "用于 --scene 参数的最佳简洁场景描述，例如 '旧海边码头与船厂'",
  "新画面风格": "用于 --visual-style 参数的最佳画面风格设定，例如 '海滨写实电影风格，带有一丝咸湿海风与怀旧暖色调'"
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
            f.write(f"## 🎨 核心视觉资产说明\n\n")
            f.write(f"在运行脚本后，系统已针对生成的详细剧本分镜自动提取出独立的角色与场景资产。\n")
            f.write(f"具体资产生图提示词，请参阅新生成的独立文件：\n")
            f.write(f"- [核心视觉资产生图提示词 (asset_prompts.md)](asset_prompts.md)\n")
            f.write(f"- 绑定关联元数据：`assets_metadata.json`\n\n")
            f.write(f"---\n\n")
            f.write(f"## 详细对比评估内容\n\n")
            f.write(report)
            f.write(f"\n\n---\n*评估报告生成时间: 2026-06-12*")

        logger.info(f"评估报告生成成功，已保存至: {report_path}")
        logger.info(f"评估结果为 方案 {winning_idx}《{winning_title}》 最为适合。")
        
        # 6. 自动化执行最优方案
        logger.info(f"【自动化执行】启动步骤 1/4: 重新改写剧本 (generate_new_script.py)...")
        # 构造执行命令行参数
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
        
        # 统一子进程环境变量为 UTF-8 编码，防止中文在管道传输中产生乱码
        sub_env = os.environ.copy()
        sub_env["PYTHONIOENCODING"] = "utf-8"
        sub_env["PYTHONUTF8"] = "1"
        
        logger.info(f"正在运行: {' '.join(cmd_rewrite[:10])} ...")
        res_rewrite = subprocess.run(cmd_rewrite, capture_output=True, text=True, encoding="utf-8", errors="replace", env=sub_env)
        if res_rewrite.returncode != 0:
            logger.error(f"剧本改写脚本运行失败！错误日志：\n{res_rewrite.stderr}")
            sys.exit(1)
        logger.info("剧本改写脚本成功运行完成！")
        
        logger.info(f"【自动化执行】启动步骤 2/4: 动态提取视觉资产提示词 (extract_assets.py)...")
        cmd_extract = [
            sys.executable,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "extract_assets.py"),
            "--api-key", api_key,
            "--model", args.model,
            "--base-url", args.base_url,
            "--csv-input", csv_path,
            "--output-dir", output_dir,
            "--storyline-title", winning_title,
            "--storyline", winning_desc
        ]
        logger.info(f"正在运行: {' '.join(cmd_extract[:10])} ...")
        res_extract = subprocess.run(cmd_extract, capture_output=True, text=True, encoding="utf-8", errors="replace", env=sub_env)
        if res_extract.returncode != 0:
            logger.error(f"资产提取脚本运行失败！错误日志：\n{res_extract.stderr}")
            sys.exit(1)
        logger.info("资产提取脚本成功运行完成！")

        logger.info(f"【自动化执行】启动步骤 3/4: 智能资产绑定 (bind_assets.py)...")
        cmd_bind = [
            sys.executable,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "bind_assets.py"),
            "--api-key", api_key,
            "--model", args.model,
            "--base-url", args.base_url,
            "--csv-input", csv_path,
            "--output-dir", output_dir
        ]
        logger.info(f"正在运行: {' '.join(cmd_bind[:10])} ...")
        res_bind = subprocess.run(cmd_bind, capture_output=True, text=True, encoding="utf-8", errors="replace", env=sub_env)
        if res_bind.returncode != 0:
            logger.warning(f"资产绑定脚本运行失败（非致命，将回退到规则匹配）：\n{res_bind.stderr}")
        else:
            logger.info("智能资产绑定脚本成功运行完成！")

        logger.info(f"【自动化执行】启动步骤 4/4: 生成视频重绘提示词 (generate_video_prompts.py)...")
        cmd_prompts = [
            sys.executable,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_video_prompts.py"),
            "--csv-input", csv_path,
            "--output-dir", output_dir
        ]
        
        logger.info(f"正在运行: {' '.join(cmd_prompts)} ...")
        res_prompts = subprocess.run(cmd_prompts, capture_output=True, text=True, encoding="utf-8", errors="replace", env=sub_env)
        if res_prompts.returncode != 0:
            logger.error(f"重绘提示词生成脚本运行失败！错误日志：\n{res_prompts.stderr}")
            sys.exit(1)
        logger.info("重绘提示词生成脚本成功运行完成！")
        
    except Exception as e:
        logger.error(f"解析大模型评估 JSON 失败: {e}。原始返回文本：\n{response_text}")
        sys.exit(1)

if __name__ == "__main__":
    main()
