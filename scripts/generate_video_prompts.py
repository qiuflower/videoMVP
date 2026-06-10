# -*- coding: utf-8 -*-
"""
脚本名称: generate_video_prompts.py
描述: 
    读取已改写的剧本分镜 CSV 数据，根据每个镜头的原有参数（景别、运镜、时长）以及
    全新构思的画面内容与台词，自动生成符合标准模板的视频重绘提示词（Video Redraw Prompts）。
    并将生成的提示词更新并导出到统一的 storyboard.csv 和 storyboard.md 中，
    方便直接导入到 AI 视频生成工具中进行重绘。
输入:
    - storyboard.csv: 包含新改写创意剧本的分镜数据表
输出:
    - storyboard.csv: 更新后包含“视频重绘提示词”列的 CSV 数据表
    - storyboard.md: 更新后包含“视频重绘提示词”列的 Markdown 分镜剧本
"""
import os
import sys
import csv
import argparse

# 动态添加项目根目录到 sys.path，支持在任意目录下运行该脚本
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import DEFAULT_STORYBOARD_CSV, DEFAULT_OUTPUT_DIR
from core.utils import get_logger

logger = get_logger("video_prompts")

def main():
    default_csv = DEFAULT_STORYBOARD_CSV
    if not os.path.exists(default_csv):
        fallback_csv = os.path.join(DEFAULT_OUTPUT_DIR, "new_script.csv")
        if os.path.exists(fallback_csv):
            default_csv = fallback_csv

    parser = argparse.ArgumentParser(description="根据原镜头参数与新剧本生成符合严格模板的视频重绘提示词")
    parser.add_argument("--csv-input", default=default_csv, help="主分镜 CSV 路径")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="输出目录")
    args = parser.parse_args()

    csv_path = os.path.abspath(args.csv_input)
    if not os.path.exists(csv_path):
        logger.error(f"未找到主分镜 CSV 文件: {csv_path}")
        sys.exit(1)

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # 读取分镜与新剧本数据
    script_records = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            script_records.append(row)

    logger.info(f"成功读取到 {len(script_records)} 个镜头剧本。")
    logger.info("正在根据用户的严格标准模板生成视频重绘提示词 (Video Redraw Prompts)...")

    prompt_records = []
    for r in script_records:
        shot_id = r["镜号"]
        scale = r["景别"]
        movement = r["运动镜头"]
        duration = r.get("时长(秒)", r.get("时长", ""))
        new_content = r.get("新画面内容", "")
        dialogue = r.get("新台词/旁白", r.get("新台词", ""))
        audio = r.get("新音效/音乐", r.get("新音效", ""))
        preview = r.get("预览图", "")
        orig_content = r.get("原画面内容", r.get("画面内容", ""))
        orig_dialogue = r.get("原台词/旁白", r.get("台词/旁白", ""))
        orig_audio = r.get("原音效/音乐", r.get("音效/音乐", ""))

        # 判定参考人像角色
        target_char = r.get("参考角色", "").strip()
        if not target_char:
            target_char = "主角林艾"
            if "陈教授" in new_content and "林艾" in new_content:
                target_char = "林艾与陈教授"
            elif "陈教授" in new_content:
                target_char = "陈教授"
            elif "同事" in new_content:
                target_char = "林艾与同事"

        # 使用用户提供的精确指令模板
        prompt = (
            f"根据原视频中的景别（{scale}）、运动镜头（{movement}），将场景人物和画面内容替换成：【{new_content}】。"
            f"同时，将场景人物替换成如图所示的参考人像（{target_char}）的样貌和场景。新台词为：【{dialogue}】。时长为 {duration}秒。"
        )

        prompt_records.append({
            "镜号": shot_id,
            "景别": scale,
            "运动镜头": movement,
            "时长(秒)": duration,
            "原画面内容": orig_content,
            "原台词/旁白": orig_dialogue,
            "原音效/音乐": orig_audio,
            "新画面内容": new_content,
            "参考角色": target_char,
            "新台词/旁白": dialogue,
            "新音效/音乐": audio,
            "视频重绘提示词": prompt,
            "预览图": preview
        })

    # 尝试从现有的 storyboard.md 中读取故事标题以保持一致
    story_title = "智能重绘"
    storyboard_md_path = os.path.join(output_dir, "storyboard.md")
    if os.path.exists(storyboard_md_path):
        try:
            with open(storyboard_md_path, "r", encoding="utf-8") as f_md:
                first_line = f_md.readline().strip()
                if first_line.startswith("#"):
                    title_part = first_line.replace("#", "").split("——")[0].strip()
                    if title_part:
                        story_title = title_part
        except Exception as e:
            pass

    # 1. 导出/覆写主分镜 Markdown 文件
    md_path = os.path.join(output_dir, "storyboard.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {story_title} —— 视频分镜剧本\n\n")
        f.write("此分镜剧本基于原视频节奏，由大语言模型重构，保持了镜头规格、运镜和时长 100% 对应。\n\n")
        f.write("| 镜号 | 镜头预览 | 镜头参数 | 原片分镜参考 | 全新创意剧本 | 视频重绘提示词 |\n")
        f.write("| --- | --- | --- | --- | --- | --- |\n")
        for rec in prompt_records:
            img_md = f"![镜号 {rec['镜号']}]({rec['预览图']})" if rec['预览图'] else "无"
            
            # 镜头参数
            param_str = f"景别：{rec['景别']}<br>运镜：{rec['运动镜头']}<br>时长：{rec['时长(秒)']}秒"
            
            # 原片分镜参考
            orig_content_clean = rec['原画面内容'].replace("\n", "<br>")
            orig_dialogue_clean = rec['原台词/旁白'].replace("\n", "<br>")
            orig_audio_clean = rec['原音效/音乐'].replace("\n", "<br>")
            ref_str = f"【画面内容】{orig_content_clean}<br>【台词/旁白】{orig_dialogue_clean}<br>【音效/音乐】{orig_audio_clean}"
            
            # 全新创意剧本
            new_content_clean = rec['新画面内容'].replace("\n", "<br>")
            char_clean = rec['参考角色'].replace("\n", "<br>")
            new_dialogue_clean = rec['新台词/旁白'].replace("\n", "<br>")
            new_audio_clean = rec['新音效/音乐'].replace("\n", "<br>")
            script_str = f"【新画面】{new_content_clean}<br>【角色】{char_clean}<br>【新台词】{new_dialogue_clean}<br>【新音效】{new_audio_clean}"
            
            prompt_clean = rec['视频重绘提示词'].replace("\n", "<br>")
            
            f.write(f"| {rec['镜号']} | {img_md} | {param_str} | {ref_str} | {script_str} | {prompt_clean} |\n")

    # 2. 导出/覆写主分镜 CSV 文件
    csv_path_out = os.path.join(output_dir, "storyboard.csv")
    csv_headers = [
        "镜号", "景别", "运动镜头", "时长(秒)", 
        "原画面内容", "原台词/旁白", "原音效/音乐",
        "新画面内容", "参考角色", "新台词/旁白", "新音效/音乐", 
        "预览图", "视频重绘提示词"
    ]
    with open(csv_path_out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(csv_headers)
        for rec in prompt_records:
            writer.writerow([
                rec["镜号"],
                rec["景别"],
                rec["运动镜头"],
                rec["时长(秒)"],
                rec["原画面内容"],
                rec["原台词/旁白"],
                rec["原音效/音乐"],
                rec["新画面内容"],
                rec["参考角色"],
                rec["新台词/旁白"],
                rec["新音效/音乐"],
                rec["预览图"],
                rec["视频重绘提示词"]
            ])

    # 3. 清理残余的旧分散文件（若存在）
    for file_name in ["new_script.csv", "new_script.md", "video_prompts.csv", "video_prompts.md"]:
        path_to_del = os.path.join(output_dir, file_name)
        if os.path.exists(path_to_del):
            try:
                os.remove(path_to_del)
                logger.info(f"成功清理残余的旧文件: {file_name}")
            except Exception as e:
                logger.warning(f"无法清理旧文件 {file_name}: {e}")

    logger.info("视频重绘提示词已成功合并追加至单一主文件！")
    logger.info(f"Markdown 主分镜剧本（含重绘提示词）已更新至: {md_path}")
    logger.info(f"CSV 主分镜数据表已更新至: {csv_path_out}")

if __name__ == "__main__":
    main()
