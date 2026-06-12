# -*- coding: utf-8 -*-
"""
脚本名称: generate_creative_storylines.py
描述: 
    根据原视频分镜的节奏与景别时长（通过分镜 CSV 输入），利用大语言模型（LLM）
    智能脑暴出 3 种全新的、且与原视频节奏高度契合的创意故事线。
    主要用于为后续视频剧本改写提供基础大纲。
输入:
    - storyboard.csv: 原视频镜头分割及画面描述数据。
输出:
    - storyline_ideas.md: 包含 3 种新故事线大纲的推荐文档，并附带一键生成新剧本的命令。
"""
import os
import sys
import json
import csv
import argparse
import time

# 动态添加项目根目录到 sys.path，支持在任意目录下运行该脚本
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import DEFAULT_STORYBOARD_CSV, DEFAULT_OUTPUT_DIR, DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_API_KEY
from core.llm_client import call_t8star_llm
from core.utils import clean_json_response, get_logger

logger = get_logger("brainstorm")

def main():
    parser = argparse.ArgumentParser(description="根据原镜头节奏智能脑暴出 3 种新剧本故事线")
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

    csv_path = os.path.abspath(args.csv_input)
    if not os.path.exists(csv_path):
        logger.error(f"未找到原分镜 CSV 文件: {csv_path}")
        sys.exit(1)

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # 读取原有分镜数据并做极简压缩（提取核心画面内容即可），避免 token 溢出
    scenes_summary = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scenes_summary.append({
                "镜号": row["镜号"],
                "景别": row["景别"],
                "时长": row["时长(秒)"],
                "运镜": row["运动镜头"],
                "原内容": row["画面内容"][:40] + "..." if len(row["画面内容"]) > 40 else row["画面内容"]
            })

    scenes_json_str = json.dumps(scenes_summary, ensure_ascii=False, indent=2)

    logger.info(f"正在使用模型 {args.model} 脑暴新故事线...")

    # 从 prompts/brainstorm_prompt.txt 载入脑暴提示词模板
    prompt_template_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "brainstorm_prompt.txt")
    if os.path.exists(prompt_template_file):
        with open(prompt_template_file, "r", encoding="utf-8") as f_prompt:
            brainstorm_prompt_template = f_prompt.read()
    else:
        # 如果文件不存在，回退到默认模板
        brainstorm_prompt_template = """您是一位天才的电影编剧和创意总监。
下面是一段原视频的 38 个镜头数据。我们需要为它重构 3 个完全不同的创意故事线大纲。
原片镜头数据摘要：
{scenes_json_str}
请严格输出 JSON：
{
  "故事线列表": []
}"""

    prompt = brainstorm_prompt_template.replace("{scenes_json_str}", scenes_json_str)

    response_text = call_t8star_llm(api_key, args.base_url, args.model, prompt)
    if not response_text:
        logger.error("大模型未能返回脑暴故事线。")
        sys.exit(1)

    cleaned_json = clean_json_response(response_text)
    
    try:
        data = json.loads(cleaned_json)
        ideas = []
        if isinstance(data, dict):
            for val in data.values():
                if isinstance(val, list):
                    ideas = val
                    break
        elif isinstance(data, list):
            ideas = data
            
        if not ideas:
            raise ValueError("未能解析出列表结构")
            
        # 写入 Markdown 脑暴推荐文档
        md_path = os.path.join(output_dir, "storyline_ideas.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# 视频分镜脑暴：3 个全新创意故事线推荐\n\n")
            f.write("这些故事线是由大语言模型通过分析原视频的运镜节奏、景别时长与情感波澜智能生成，您可以任选其一用于新剧本的自动改写。\n\n")
            
            for idx, idea in enumerate(ideas):
                f.write(f"## 方案 {idx+1}：{idea.get('标题', '未命名故事')}\n\n")
                f.write(f"- **核心题材**：{idea.get('核心题材', '未知')}\n")
                f.write(f"- **角色角色对照**：{idea.get('角色定义', '未知')}\n")
                f.write(f"- **情绪阶段映射**：{idea.get('阶段映射说明', '未知')}\n\n")
                f.write(f"### 故事大纲：\n> {idea.get('故事大纲', '无')}\n\n")
                
                # 附带运行命令提示，极大增强易用性
                cmd_run = f"python scripts/generate_new_script.py --storyline \"{idea.get('故事大纲', '')}\" --storyline-title \"{idea.get('标题', '')}\""
                f.write("#### 💡 一键运行改写此剧本命令：\n")
                f.write(f"```powershell\n{cmd_run}\n```\n\n")
                f.write("---\n\n")
                
        logger.info(f"故事线脑暴成功！3个推荐的故事线方案已写入: {md_path}")
        
    except Exception as e:
        logger.error(f"解析大模型脑暴 JSON 失败: {e}。原始返回文本：\n{response_text}")
        sys.exit(1)

if __name__ == "__main__":
    main()
