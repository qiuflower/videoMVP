# -*- coding: utf-8 -*-
"""
脚本名称: generate_new_script.py
描述: 
    根据指定的全新创意故事线大纲（Storyline），使用大语言模型（LLM）逐批次（每 6 镜一组）
    对原有视频分镜剧本进行改写。该脚本会保持原分镜的镜头景别、运镜和时长 100% 对应，
    重新构思画面内容、角色设计、新台词/旁白以及新音效/音乐。
    最后将生成的新剧本数据合并并输出到统一的 storyboard.csv 和 storyboard.md 中。
输入:
    - storyboard.csv: 原视频分镜数据（作为结构参考）
    - 命令行传入的故事大纲与标题（或使用默认故事线）
输出:
    - storyboard.csv: 更新后包含新创意剧本与原分镜对照的 CSV 数据表
    - storyboard.md: 更新后包含镜头预览、参数及原新对照的 Markdown 分镜剧本
"""
import os
import sys
import json
import csv
import argparse
import time

# 动态添加项目根目录到 sys.path，支持在任意目录下运行该脚本
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import DEFAULT_STORYBOARD_CSV, DEFAULT_OUTPUT_DIR
from core.llm_client import call_t8star_llm
from core.utils import clean_json_response, get_logger

logger = get_logger("rewrite_script")

def main():
    parser = argparse.ArgumentParser(description="根据原分镜节奏生成全新故事剧本")
    parser.add_argument("--api-key", help="t8star API Key")
    parser.add_argument("--model", default="gpt-5.4-mini-2026-03-17", help="调用的模型名称")
    parser.add_argument("--base-url", default="https://ai.t8star.org/v1", help="API 的 baseurl 路径")
    parser.add_argument("--csv-input", default=DEFAULT_STORYBOARD_CSV, help="原分镜 CSV 路径")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="输出目录")
    parser.add_argument("--storyline", default="", help="新故事的大纲，如果提供则使用该大纲进行改写")
    parser.add_argument("--storyline-title", default="", help="新故事的标题，配合--storyline使用")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("T8STAR_API_KEY") or os.environ.get("OPENAI_API_KEY")
    
    storyline_title = args.storyline_title or "创意重塑：设计师的灵感突破"
    storyline_desc = args.storyline or (
        "林艾是一名年轻的UI/UX设计师，面临严重的灵感枯竭和创意瓶颈（前段：镜头001-007）。"
        "她在园区中踱步，回忆起童年无拘无束画画的心态，并四处观察生活中的点滴（中段：镜头008-024）。"
        "在经历挫折和迷茫（后段：镜头025-030）后，他在长椅上偶遇了退休设计大师陈教授，通过一番深入温馨的交谈，解开了心结（结尾：镜头031-038）。"
    )
    if not api_key:
        logger.error("缺少 API Key，请在根目录 .env 文件中配置 T8STAR_API_KEY。")
        sys.exit(1)

    csv_path = os.path.abspath(args.csv_input)
    if not os.path.exists(csv_path):
        logger.error(f"未找到原分镜 CSV 文件: {csv_path}")
        sys.exit(1)

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # 读取原有分镜数据
    original_scenes = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            original_scenes.append(row)

    logger.info(f"成功读取到 {len(original_scenes)} 个分镜镜头。")
    logger.info(f"正在使用模型 {args.model} 通过 LLM 自动改写新剧本...")
    logger.info(f"新故事线大纲：《{storyline_title}》")

    # 按照每 6 镜为一组进行分批请求，保证叙事连贯且大模型不发生混淆或字段遗漏
    batch_size = 6
    rewritten_records = {}

    # 从 prompts/rewrite_prompt.txt 载入剧本改写提示词模板
    prompt_template_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "rewrite_prompt.txt")
    if os.path.exists(prompt_template_file):
        with open(prompt_template_file, "r", encoding="utf-8") as f_prompt:
            rewrite_prompt_template = f_prompt.read()
    else:
        # 如果文件不存在，回退到默认模板
        rewrite_prompt_template = """你是一个顶级的编剧和分镜导演。我们需要把一部原片改写成《{storyline_title}》。
故事大纲：
{storyline_desc}
目前我们需要改写第 {start_num} 镜 到 第 {end_num} 镜。
原分镜数据：
{scenes_json_str}
请严格输出 JSON：
{
  "剧本": []
}"""

    for i in range(0, len(original_scenes), batch_size):
        batch = original_scenes[i:i+batch_size]
        start_num = batch[0]["镜号"]
        end_num = batch[-1]["镜号"]
        
        logger.info(f"正在处理第 {start_num} 镜 到 第 {end_num} 镜...")
        
        # 构建当前批次的输入数据
        batch_input = []
        for s in batch:
            batch_input.append({
                "镜号": s["镜号"],
                "景别": s["景别"],
                "运动镜头": s["运动镜头"],
                "时长": s["时长(秒)"],
                "原画面内容": s["画面内容"]
            })
            
        scenes_json_str = json.dumps(batch_input, ensure_ascii=False, indent=2)
        
        # 4. 构建提示词，通过 .replace 替换占位符
        prompt = rewrite_prompt_template \
            .replace("{storyline_title}", storyline_title) \
            .replace("{storyline_desc}", storyline_desc) \
            .replace("{start_num}", start_num) \
            .replace("{end_num}", end_num) \
            .replace("{scenes_json_str}", scenes_json_str)
        
        response_text = call_t8star_llm(api_key, args.base_url, args.model, prompt, temperature=0.3)
        
        if not response_text:
            logger.error(f"获取批次 {start_num}-{end_num} 响应失败。填充默认值...")
            for s in batch:
                rewritten_records[s["镜号"]] = {
                    "新画面内容": f"（改写失败）新故事画面，原内容为：{s['画面内容']}",
                    "参考角色": "主角",
                    "新台词_旁白": "无",
                    "新音效_音乐": "无"
                }
            continue

        cleaned_json = clean_json_response(response_text)
        
        try:
            data = json.loads(cleaned_json)
            items = []
            if isinstance(data, dict):
                # 寻找字典中任意一个是列表的键值对
                for val in data.values():
                    if isinstance(val, list):
                        items = val
                        break
                else:
                    # 如果没找到列表，看看是不是以镜号为 key 的字典结构
                    for k, v in data.items():
                        if isinstance(v, dict):
                            v["镜号"] = k
                            items.append(v)
            elif isinstance(data, list):
                items = data
                
            if not items:
                raise ValueError("解析出来的结果不包含任何有效的列表或字典结构")
                
            for item in items:
                shot_id = str(item.get("镜号", "")).zfill(3)
                rewritten_records[shot_id] = {
                    "新画面内容": item.get("新画面内容", item.get("画面内容", "画面内容未生成")),
                    "参考角色": item.get("参考角色", "主角"),
                    "新台词_旁白": item.get("新台词_旁白", item.get("台词/旁白", item.get("台词", "无"))),
                    "新音效_音乐": item.get("新音效_音乐", item.get("音效/音乐", item.get("音效", "无")))
                }
                
        except Exception as e:
            logger.error(f"解析批次 {start_num}-{end_num} JSON 失败: {e}。开始使用文本模糊匹配...")
            # 备用匹配逻辑
            import re
            for s in batch:
                shot_id = s["镜号"]
                # 寻找每个镜号的块
                pattern = r'"' + re.escape(shot_id) + r'".*?\n\s*\}\n'
                block_match = re.search(pattern, cleaned_json, re.DOTALL)
                if block_match:
                    block = block_match.group(0)
                    content_m = re.search(r'"新画面内容"\s*:\s*"([^"]+)"', block)
                    char_m = re.search(r'"参考角色"\s*:\s*"([^"]+)"', block)
                    dialogue_m = re.search(r'"新台词_旁白"\s*:\s*"([^"]+)"', block)
                    audio_m = re.search(r'"新音效_音乐"\s*:\s*"([^"]+)"', block)
                    rewritten_records[shot_id] = {
                        "新画面内容": content_m.group(1) if content_m else f"新故事画面",
                        "参考角色": char_m.group(1) if char_m else "主角",
                        "新台词_旁白": dialogue_m.group(1) if dialogue_m else "无",
                        "新音效_音乐": audio_m.group(1) if audio_m else "无"
                    }
                else:
                    rewritten_records[shot_id] = {
                        "新画面内容": f"设计灵感画面 (原内容: {s['画面内容'][:20]}...)",
                        "参考角色": "主角",
                        "新台词_旁白": "无",
                        "新音效_音乐": "无"
                    }

    # 合并数据并输出新剧本
    new_script_records = []
    for orig in original_scenes:
        shot_id = orig["镜号"]
        rewritten = rewritten_records.get(shot_id, {
            "新画面内容": "改写缺失",
            "参考角色": "主角",
            "新台词_旁白": "无",
            "新音效_音乐": "无"
        })
        
        record = {
            "镜号": shot_id,
            "景别": orig.get("景别", ""),
            "运动镜头": orig.get("运动镜头", ""),
            "时长(秒)": orig.get("时长(秒)", orig.get("时长", "")),
            "原画面内容": orig.get("画面内容", orig.get("原画面内容", "")),
            "原台词/旁白": orig.get("台词/旁白", orig.get("原台词/旁白", "")),
            "原音效/音乐": orig.get("音效/音乐", orig.get("原音效/音乐", "")),
            "新画面内容": rewritten["新画面内容"],
            "参考角色": rewritten["参考角色"],
            "新台词/旁白": rewritten["新台词_旁白"],
            "新音效/音乐": rewritten["新音效_音乐"],
            "预览图": orig.get("预览图", orig.get("本地预览图路径", ""))
        }
        
        # 保留以后步骤生成的提示词列
        if "视频重绘提示词" in orig:
            record["视频重绘提示词"] = orig["视频重绘提示词"]
            
        new_script_records.append(record)

    # 1. 导出/覆写主分镜 Markdown 文件
    md_path = os.path.join(output_dir, "storyboard.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {storyline_title} —— 视频分镜剧本\n\n")
        f.write("此分镜剧本基于原视频节奏，由大语言模型重构，保持了镜头规格、运镜和时长 100% 对应。\n\n")
        
        # 判断是否包含提示词列，动态生成表头
        has_prompt = any("视频重绘提示词" in r for r in new_script_records)
        if has_prompt:
            f.write("| 镜号 | 镜头预览 | 镜头参数 | 原片分镜参考 | 全新创意剧本 | 视频重绘提示词 |\n")
            f.write("| --- | --- | --- | --- | --- | --- |\n")
        else:
            f.write("| 镜号 | 镜头预览 | 镜头参数 | 原片分镜参考 | 全新创意剧本 |\n")
            f.write("| --- | --- | --- | --- | --- |\n")
            
        for r in new_script_records:
            img_md = f"![镜号 {r['镜号']}]({r['预览图']})" if r['预览图'] else "无"
            
            # 镜头参数
            param_str = f"景别：{r['景别']}<br>运镜：{r['运动镜头']}<br>时长：{r['时长(秒)']}秒"
            
            # 原片分镜参考
            orig_content_clean = r['原画面内容'].replace("\n", "<br>")
            orig_dialogue_clean = r['原台词/旁白'].replace("\n", "<br>")
            orig_audio_clean = r['原音效/音乐'].replace("\n", "<br>")
            ref_str = f"【画面内容】{orig_content_clean}<br>【台词/旁白】{orig_dialogue_clean}<br>【音效/音乐】{orig_audio_clean}"
            
            # 全新创意剧本
            new_content_clean = r['新画面内容'].replace("\n", "<br>")
            char_clean = r['参考角色'].replace("\n", "<br>")
            new_dialogue_clean = r['新台词/旁白'].replace("\n", "<br>")
            new_audio_clean = r['新音效/音乐'].replace("\n", "<br>")
            script_str = f"【新画面】{new_content_clean}<br>【角色】{char_clean}<br>【新台词】{new_dialogue_clean}<br>【新音效】{new_audio_clean}"
            
            if has_prompt:
                prompt_clean = r.get('视频重绘提示词', '未生成').replace("\n", "<br>")
                f.write(f"| {r['镜号']} | {img_md} | {param_str} | {ref_str} | {script_str} | {prompt_clean} |\n")
            else:
                f.write(f"| {r['镜号']} | {img_md} | {param_str} | {ref_str} | {script_str} |\n")

    # 2. 导出/覆写主分镜 CSV 文件
    csv_path_out = os.path.join(output_dir, "storyboard.csv")
    csv_headers = [
        "镜号", "景别", "运动镜头", "时长(秒)", 
        "原画面内容", "原台词/旁白", "原音效/音乐",
        "新画面内容", "参考角色", "新台词/旁白", "新音效/音乐", 
        "预览图"
    ]
    if has_prompt:
        csv_headers.append("视频重绘提示词")
        
    with open(csv_path_out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(csv_headers)
        for r in new_script_records:
            row_data = [
                r["镜号"],
                r["景别"],
                r["运动镜头"],
                r["时长(秒)"],
                r["原画面内容"],
                r["原台词/旁白"],
                r["原音效/音乐"],
                r["新画面内容"],
                r["参考角色"],
                r["新台词/旁白"],
                r["新音效/音乐"],
                r["预览图"]
            ]
            if has_prompt:
                row_data.append(r.get("视频重绘提示词", ""))
            writer.writerow(row_data)

    # 3. 清理残余的旧分散文件（若存在）
    for file_name in ["new_script.csv", "new_script.md"]:
        path_to_del = os.path.join(output_dir, file_name)
        if os.path.exists(path_to_del):
            try:
                os.remove(path_to_del)
                logger.info(f"成功清理残余的旧文件: {file_name}")
            except Exception as e:
                logger.warning(f"无法清理旧文件 {file_name}: {e}")

    logger.info("剧本数据已成功合并追加至单一主文件！")
    logger.info(f"Markdown 主分镜剧本已更新至: {md_path}")
    logger.info(f"CSV 主分镜数据表已更新至: {csv_path_out}")

if __name__ == "__main__":
    main()
