# -*- coding: utf-8 -*-
"""
脚本名称: generate_storyboard.py
描述: 
    对切分后的视频镜头片段（mp4）进行自动分析。它首先通过 ffprobe 获取镜头时长，
    然后调用 FFmpeg 提取每个镜头的关键帧图像。将关键帧图像转换为 Base64 格式后，
    调用大语言模型（LLM）的多模态视觉 API 对画面的景别、运镜、画面内容、字幕/台词
    及音效/音乐进行智能识别与分析，并导出为结构化的 storyboard.csv 和 storyboard.md 分镜表。
输入:
    - 切分后的视频片段目录（由 --scenes-dir 参数指定）
输出:
    - keyframes/: 提取的各个镜头关键帧 JPG 图片
    - storyboard.csv: 包含所有镜头基本属性与分析内容的 CSV 分镜数据表
    - storyboard.md: 支持本地关键帧图片预览的 Markdown 格式详细分镜表
"""
import os
import sys
import json
import glob
import subprocess
import base64
import csv
import argparse
import time
from tqdm import tqdm

# 动态添加项目根目录到 sys.path，支持在任意目录下运行该脚本
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import DEFAULT_OUTPUT_SCENES_DIR, DEFAULT_OUTPUT_DIR
from core.llm_client import call_t8star_vision_api
from core.utils import clean_json_response, get_logger

logger = get_logger("extract_storyboard")

def get_video_duration(video_path):
    """使用 ffprobe 获取视频时长"""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception as e:
        logger.warning(f"无法获取视频 {os.path.basename(video_path)} 的时长，默认设为 5.0 秒。错误: {e}")
        return 5.0

def extract_keyframes(video_path, duration, keyframes_dir, scene_prefix):
    """利用 FFmpeg 在指定时间点截取关键帧"""
    # 动态计算截图的时间点
    if duration <= 1.0:
        timestamps = [duration / 2.0]
    elif duration <= 2.0:
        timestamps = [duration * 0.25, duration * 0.75]
    else:
        timestamps = [duration * 0.1, duration * 0.5, duration * 0.9]

    extracted_files = []
    for idx, ts in enumerate(timestamps):
        out_name = f"{scene_prefix}_frame_{idx + 1}.jpg"
        out_path = os.path.join(keyframes_dir, out_name)
        
        # FFmpeg 命令：使用 -ss 定位并截图一张
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{ts:.3f}",
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "2",
            out_path
        ]
        
        try:
            # 隐藏输出运行 ffmpeg
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                extracted_files.append(out_path)
        except Exception as e:
            logger.warning(f"镜头 {scene_prefix} 提取 {ts}s 处的关键帧失败: {e}")
            
    return extracted_files

def encode_image_to_base64(image_path):
    """将本地图像文件转为 base64 字符串"""
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode("utf-8")

def parse_llm_json(content):
    """解析并提取 JSON 中的分镜字段，若解析失败则使用备用匹配机制"""
    default_data = {
        "景别": "未知",
        "运动镜头": "未知",
        "画面内容": "解析失败，原始内容：" + str(content),
        "台词_旁白": "无",
        "音效_音乐": "无"
    }
    
    if not content:
        return default_data
        
    cleaned = clean_json_response(content)
    
    try:
        data = json.loads(cleaned)
        # 统一键名，防止 LLM 返回的 key 略有差异
        result = {}
        result["景别"] = data.get("景别", data.get("景别选择", "中景"))
        result["运动镜头"] = data.get("运动镜头", data.get("运镜", "固定"))
        result["画面内容"] = data.get("画面内容", data.get("内容", cleaned))
        result["台词_旁白"] = data.get("台词_旁白", data.get("台词/旁白", data.get("台词", "无")))
        result["音效_音乐"] = data.get("音效_音乐", data.get("音效/音乐", data.get("音效", "无")))
        return result
    except Exception as e:
        # 正则备用匹配
        import re
        result = default_data.copy()
        for key in ["景别", "运动镜头", "画面内容"]:
            match = re.search(fr'"{key}"\s*:\s*"([^"]+)"', cleaned)
            if match:
                result[key] = match.group(1)
        
        # 提取台词/音效
        match_dialogue = re.search(r'"(?:台词_旁白|台词/旁白|台词)"\s*:\s*"([^"]+)"', cleaned)
        if match_dialogue:
            result["台词_旁白"] = match_dialogue.group(1)
            
        match_audio = re.search(r'"(?:音效_音乐|音效/音乐|音效)"\s*:\s*"([^"]+)"', cleaned)
        if match_audio:
            result["音效_音乐"] = match_audio.group(1)
            
        return result

def main():
    parser = argparse.ArgumentParser(description="使用 t8star LLM 批量生成视频镜头分镜表")
    parser.add_argument("--api-key", help="t8star API 密钥。也可以设置环境变量 T8STAR_API_KEY")
    parser.add_argument("--model", default="gpt-5.4-mini-2026-03-17", help="调用的模型名称")
    parser.add_argument("--base-url", default="https://ai.t8star.org/v1", help="API 的 baseurl 路径")
    parser.add_argument("--scenes-dir", default=DEFAULT_OUTPUT_SCENES_DIR, help="切分视频片段所在目录")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="分镜表等结果输出目录")
    args = parser.parse_args()

    # 获取 API Key
    api_key = args.api_key or os.environ.get("T8STAR_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("缺少 API Key！请在 .env 文件中配置 T8STAR_API_KEY，或者在运行时使用 --api-key 传入参数。")
        sys.exit(1)

    # 确定路径
    scenes_dir = os.path.abspath(args.scenes_dir)
    output_dir = os.path.abspath(args.output_dir)
    keyframes_dir = os.path.join(output_dir, "keyframes")

    # 创建必要的目录
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(keyframes_dir, exist_ok=True)

    # 查找所有的 mp4 视频片段并排序
    # 匹配模式形如 output_scenes/38066130121-1-192-Scene-001.mp4 或类似文件
    video_patterns = [
        os.path.join(scenes_dir, "*-Scene-*.mp4"),
        os.path.join(scenes_dir, "Scene-*.mp4"),
        os.path.join(scenes_dir, "*.mp4")
    ]
    
    video_files = []
    for pattern in video_patterns:
        matched = glob.glob(pattern)
        if matched:
            video_files = matched
            break

    # 排除预览文件或非镜头切片文件
    video_files = [f for f in video_files if not os.path.basename(f).endswith("_preview.mp4")]
    
    if not video_files:
        logger.error(f"未在 {scenes_dir} 中找到切分的视频片段。请先确保完成了视频分切。")
        sys.exit(1)
        
    video_files.sort()
    logger.info(f"寻找到 {len(video_files)} 个视频片段开始处理...")
    logger.info(f"调用的模型: {args.model}")
    logger.info(f"API BaseURL: {args.base_url}")
    logger.info(f"提取的关键帧图片将被保存在: {keyframes_dir}")

    # 从 prompts/vision_prompt.txt 载入 Vision 提示词模板
    prompt_template_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "vision_prompt.txt")
    if os.path.exists(prompt_template_file):
        with open(prompt_template_file, "r", encoding="utf-8") as f_prompt:
            vision_prompt_template = f_prompt.read()
    else:
        # 如果文件不存在，回退到默认模板
        vision_prompt_template = """你是一个专业的分镜导演。请根据提供的视频片段关键帧，分析并撰写该镜头的分镜信息。
该镜头的时长为 {duration:.2f} 秒。
请输出包含以下字段的 JSON 格式数据：
- 景别：选择最符合的一项
- 运动镜头：选择最符合的一项
- 画面内容：详细描述画面中的视觉内容
- 台词_旁白：从画面中识别中文字幕
- 音效_音乐：建议最适合的背景音乐或音效
直接以双花括号包裹 JSON：
{
  "景别": "...",
  "运动镜头": "...",
  "画面内容": "...",
  "台词_旁白": "...",
  "音效_音乐": "..."
}"""

    storyboard_records = []

    for file_path in tqdm(video_files, desc="分析镜头", unit="shot"):
        file_name = os.path.basename(file_path)
        # 获取镜号。一般格式为 "XXX-Scene-001.mp4" 或者是 "Scene-001.mp4"
        # 尝试从名字中解析镜号
        scene_name_part = os.path.splitext(file_name)[0]
        if "Scene-" in scene_name_part:
            shot_num = scene_name_part.split("Scene-")[-1]
        else:
            shot_num = scene_name_part[-3:]  # 取最后三位作为默认
            
        # 1. 获取视频时长
        duration = get_video_duration(file_path)
        
        # 2. 提取关键帧
        keyframes = extract_keyframes(file_path, duration, keyframes_dir, f"scene_{shot_num}")
        
        if not keyframes:
            logger.warning(f"镜号 #{shot_num}: 无法提取关键帧，跳过大模型调用。")
            storyboard_records.append({
                "镜号": shot_num,
                "景别": "未知",
                "运动镜头": "未知",
                "时长": f"{duration:.2f}",
                "画面内容": "无法提取关键帧图像进行分析",
                "台词/旁白": "无",
                "音效/音乐": "无",
                "预览图": "无"
            })
            continue

        # 3. 将关键帧转换为 Base64
        base64_images = [encode_image_to_base64(img) for img in keyframes]
        
        # 4. 构建提示词
        prompt = vision_prompt_template.format(duration=duration)

        # 5. 调用 API
        llm_response = call_t8star_vision_api(api_key, args.base_url, args.model, prompt, base64_images)
        
        # 6. 解析结果
        parsed_data = parse_llm_json(llm_response)
        
        # 选取第 2 张图（中间帧）作为预览图在 Markdown 中展示
        preview_img_relative = ""
        if len(keyframes) >= 2:
            preview_img_relative = f"keyframes/{os.path.basename(keyframes[1])}"
        elif len(keyframes) == 1:
            preview_img_relative = f"keyframes/{os.path.basename(keyframes[0])}"
            
        storyboard_records.append({
            "镜号": shot_num,
            "景别": parsed_data["景别"],
            "运动镜头": parsed_data["运动镜头"],
            "时长": f"{duration:.2f}",
            "画面内容": parsed_data["画面内容"],
            "台词/旁白": parsed_data["台词_旁白"],
            "音效/音乐": parsed_data["音效_音乐"],
            "预览图": preview_img_relative
        })

    # ================= 导出结果 =================
    
    # 1. 写入 Markdown 分镜表 (支持嵌入本地图像预览)
    md_path = os.path.join(output_dir, "storyboard.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# 视频详细分镜脚本表\n\n")
        f.write("此分镜表由 `generate_storyboard.py` 自动生成，使用了大语言模型进行画面识别与视觉理解。\n\n")
        f.write("| 镜号 | 镜头预览 | 镜头参数 | 原片分镜参考 |\n")
        f.write("| --- | --- | --- | --- |\n")
        for rec in storyboard_records:
            # 在 Markdown 表格中渲染预览图
            img_markdown = f"![镜号 {rec['镜号']}]({rec['预览图']})" if rec['预览图'] else "无"
            
            # 整理数据为垂直紧凑格式
            param_str = f"景别：{rec['景别']}<br>运镜：{rec['运动镜头']}<br>时长：{rec['时长']}秒"
            
            content_clean = rec['画面内容'].replace("\n", "<br>")
            dialogue_clean = rec['台词/旁白'].replace("\n", "<br>")
            audio_clean = rec['音效/音乐'].replace("\n", "<br>")
            ref_str = f"【画面内容】{content_clean}<br>【台词/旁白】{dialogue_clean}<br>【音效/音乐】{audio_clean}"
            
            f.write(f"| {rec['镜号']} | {img_markdown} | {param_str} | {ref_str} |\n")
            
    # 2. 写入 CSV 分镜表
    csv_path = os.path.join(output_dir, "storyboard.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["镜号", "景别", "运动镜头", "时长(秒)", "画面内容", "台词/旁白", "音效/音乐", "预览图"])
        for rec in storyboard_records:
            writer.writerow([
                rec["镜号"],
                rec["景别"],
                rec["运动镜头"],
                rec["时长"],
                rec["画面内容"],
                rec["台词/旁白"],
                rec["音效/音乐"],
                rec["预览图"]
            ])

    logger.info(f"分镜表生成完成！共生成了 {len(storyboard_records)} 个镜头的分镜。")
    logger.info(f"Markdown 预览格式分镜表已保存至: {md_path}")
    logger.info(f"CSV/Excel 兼容格式分镜表已保存至: {csv_path}")

if __name__ == "__main__":
    main()
