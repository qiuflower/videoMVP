# -*- coding: utf-8 -*-
"""
脚本名称: generate_images.py
描述: 
    根据 storyboard.csv 中的首尾帧提示词与 output/asset_prompts.md 中的资产提示词，
    调用 gpt-image-2 大模型接口 (https://ai.t8star.org/v1/chat/completions) 自动批量生图，
    并自动将生成的图像下载并保存到本地 assets/ 目录中，激活 storyboard.md 中的图像预览。
"""
import os
import sys
import csv
import json
import re
import argparse
import requests
import time
import base64
import glob
import mimetypes
import io
from PIL import Image

# 动态添加项目根目录到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import DEFAULT_STORYBOARD_CSV, DEFAULT_OUTPUT_DIR
from core.utils import get_logger, resolve_asset_paths

logger = get_logger("generate_images")

def generate_image_via_gpt_image_2(api_key, base_url, prompt, base64_images=None):
    """调用 gpt-image-2 chat completion 生图接口，并解析返回的 Markdown 图片 URL，支持多模态双图注入"""
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    if base64_images:
        content_blocks = [{"type": "text", "text": prompt}]
        for img_b64, mime_type in base64_images:
            content_blocks.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{img_b64}"
                }
            })
        messages = [
            {
                "role": "user",
                "content": content_blocks
            }
        ]
    else:
        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]

    payload = {
        "model": "gpt-image-2",
        "messages": messages
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        # 正则解析 Markdown 格式 of 图片链接，例如 ![image](https://...)
        match = re.search(r'\((https?://[^\)]+)\)', content)
        if match:
            return match.group(1)
        else:
            logger.warning(f"无法从大模型返回的文本中解析出图片链接。返回文本：{content}")
            return None
    except Exception as e:
        logger.error(f"API 生图请求失败: {e}")
        return None

def encode_image_to_base64(image_path, max_size=(1024, 1024), quality=80):
    """读取图片文件，使用 PIL 进行缩放与 JPEG 压缩以减小体积，最后转换为 base64 字符串"""
    if not image_path or not os.path.exists(image_path):
        return None, None
    try:
        mime_type = "image/jpeg"  # 压缩后统一使用 jpeg 格式
        
        # 针对小于 200KB 的小图，直接读取，不进行重压缩以节省开销
        if os.path.getsize(image_path) < 200 * 1024:
            with open(image_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode('utf-8')
            guessed_mime, _ = mimetypes.guess_type(image_path)
            return b64_data, guessed_mime or mime_type
            
        # 否则使用 PIL 压缩
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
                
            img.thumbnail(max_size, Image.LANCZOS)
            
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality)
            b64_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            logger.info(f"图片已优化 ({os.path.basename(image_path)}): "
                        f"原始大小 {os.path.getsize(image_path)/1024:.1f}KB -> "
                        f"压缩后 {len(buffer.getvalue())/1024:.1f}KB")
            return b64_data, mime_type
    except Exception as e:
        logger.error(f"优化并转换图片失败 ({image_path}): {e}")
        try:
            mime_type, _ = mimetypes.guess_type(image_path)
            if not mime_type:
                mime_type = "image/jpeg"
            with open(image_path, "rb") as image_file:
                b64_data = base64.b64encode(image_file.read()).decode('utf-8')
                return b64_data, mime_type
        except Exception as e2:
            logger.error(f"Fallback 直接读取图片同样失败 ({image_path}): {e2}")
            return None, None

def get_first_keyframe_path(keyframes_dir, shot_id):
    """获取指定镜号的第一帧关键帧路径"""
    try:
        shot_id_str = f"{int(shot_id):03d}"
    except ValueError:
        shot_id_str = shot_id
    
    exact_path = os.path.join(keyframes_dir, f"scene_{shot_id_str}_frame_1.jpg")
    if os.path.exists(exact_path):
        return exact_path
    
    pattern = os.path.join(keyframes_dir, f"scene_{shot_id_str}_frame_*.jpg")
    matches = glob.glob(pattern)
    if matches:
        matches.sort()
        return matches[0]
    return None

def get_last_keyframe_path(keyframes_dir, shot_id):
    """获取指定镜号的最后一帧关键帧路径"""
    try:
        shot_id_str = f"{int(shot_id):03d}"
    except ValueError:
        shot_id_str = shot_id
        
    pattern = os.path.join(keyframes_dir, f"scene_{shot_id_str}_frame_*.jpg")
    matches = glob.glob(pattern)
    if matches:
        matches.sort()
        return matches[-1]
    return None

def get_character_ref_paths(row, assets_meta, project_root):
    """直接从 CSV 字段获取物理图片路径，若无绑定则使用统一的解析函数进行匹配兜底"""
    paths = []
    
    # 1. 优先读取 CSV 中的绑定物理路径
    csv_ref_path = row.get("角色参考图路径", "").strip()
    if csv_ref_path and csv_ref_path not in ["无", "无人物", "待绑定", "assets/character_ref.png"]:
        parts = re.split(r'[,;，；\s]+', csv_ref_path)
        for part in parts:
            part = part.strip()
            if part:
                # 兼容相对和绝对路径
                if os.path.isabs(part):
                    full_path = part
                else:
                    full_path = os.path.join(project_root, part)
                if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                    if full_path not in paths:
                        paths.append(full_path)
        if paths:
            return paths

    # 2. 兜底匹配：如果 CSV 字段未绑定，利用统一的工具函数解析匹配
    ref_char = row.get("参考角色", "").strip()
    if ref_char and ref_char not in ["无人物", "无"]:
        characters = assets_meta.get("characters", {})
        matched_paths, _ = resolve_asset_paths(ref_char, characters, category="characters")
        for path in matched_paths:
            full_path = os.path.join(project_root, path)
            if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                if full_path not in paths:
                    paths.append(full_path)

    # 3. 终极兜底：使用默认参考图
    if not paths:
        fallback_path = os.path.join(project_root, "assets/character_ref.png")
        if os.path.exists(fallback_path):
            paths.append(fallback_path)
            
    return paths

def get_scene_ref_paths(row, assets_meta, project_root):
    """直接从 CSV 字段获取物理场景图片路径，若无绑定则使用统一的解析函数进行匹配兜底"""
    paths = []
    
    # 1. 优先读取 CSV 中的绑定物理路径
    csv_ref_path = row.get("场景参考图路径", "").strip()
    if csv_ref_path and csv_ref_path not in ["无", "待绑定", "assets/scene_ref.png"]:
        parts = re.split(r'[,;，；\s]+', csv_ref_path)
        for part in parts:
            part = part.strip()
            if part:
                # 兼容相对和绝对路径
                if os.path.isabs(part):
                    full_path = part
                else:
                    full_path = os.path.join(project_root, part)
                if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                    if full_path not in paths:
                        paths.append(full_path)
        if paths:
            return paths

    # 2. 兜底匹配：如果 CSV 字段未绑定，利用统一的工具函数解析匹配
    ref_scene = row.get("新场景", "").strip()
    if ref_scene and ref_scene not in ["无"]:
        scenes = assets_meta.get("scenes", {})
        matched_paths, _ = resolve_asset_paths(ref_scene, scenes, category="scenes")
        for path in matched_paths:
            full_path = os.path.join(project_root, path)
            if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                if full_path not in paths:
                    paths.append(full_path)

    # 3. 终极兜底：使用默认参考图
    if not paths:
        fallback_path = os.path.join(project_root, "assets/scene_ref.png")
        if os.path.exists(fallback_path):
            paths.append(fallback_path)
            
    return paths

def download_image(url, save_path):
    """下载图片并保存至本地文件路径"""
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(response.content)
        logger.info(f"成功下载图片并保存至: {save_path}")
        return True
    except Exception as e:
        logger.error(f"下载图片失败 ({url}): {e}")
        return False

def parse_asset_prompts(md_path):
    """从 asset_prompts.md 中解析核心资产的英文提示词"""
    prompts = {}
    if not os.path.exists(md_path):
        logger.warning(f"未找到资产生图提示词文件: {md_path}")
        return prompts
        
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # 按资产块划分
    sections = content.split("## 📍 资产：")
    for section in sections[1:]:
        lines = section.split("\n")
        asset_name = lines[0].strip()
        
        # 寻找英文提示词
        eng_prompt = None
        for line in lines:
            if "英文 Prompt" in line or "英文提示词" in line or "英文 Prompt" in line:
                # 匹配反引号中的提示词内容
                match = re.search(r'`(.*?)`', line)
                if match:
                    eng_prompt = match.group(1)
                    break
        if asset_name and eng_prompt:
            prompts[asset_name] = eng_prompt
            
    return prompts

def process_and_generate_frame(shot_id, prompt, frame_type, keyframe_path, char_ref_paths, scene_ref_paths, api_key, base_url, save_path, skip_existing=True):
    """
    通用单帧图像生成与下载处理函数
    :param shot_id: 镜号
    :param prompt: 生图提示词
    :param frame_type: 帧类型 ('first' 或 'last')
    :param keyframe_path: 构图参考原片关键帧路径
    :param char_ref_paths: 角色参考图路径列表
    :param scene_ref_paths: 场景参考图路径列表
    :param api_key: API 密钥
    :param base_url: API 基础地址
    :param save_path: 目标保存路径
    :param skip_existing: 是否跳过已存在的文件
    """
    if not prompt or prompt == "无":
        return

    frame_label = "首帧" if frame_type == "first" else "尾帧"
    
    if skip_existing and os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        logger.info(f"镜号 #{shot_id}: {frame_label}图像已存在，跳过。")
        return

    if keyframe_path:
        logger.info(f"镜号 #{shot_id}: {frame_label}匹配到原始关键帧: {keyframe_path}")
    
    # 编码并组装多模态 payload
    base64_images = []
    num_char_refs = 0
    num_scene_refs = 0
    has_kf = False
    
    # 逐个对角色参考图进行 Base64 编码与优化
    if char_ref_paths:
        for path in char_ref_paths:
            char_b64, char_mime = encode_image_to_base64(path)
            if char_b64:
                base64_images.append((char_b64, char_mime))
                num_char_refs += 1
                
    # 逐个对场景参考图进行 Base64 编码与优化
    if scene_ref_paths:
        for path in scene_ref_paths:
            scene_b64, scene_mime = encode_image_to_base64(path)
            if scene_b64:
                base64_images.append((scene_b64, scene_mime))
                num_scene_refs += 1
        
    kf_b64, kf_mime = encode_image_to_base64(keyframe_path) if keyframe_path else (None, None)
    if kf_b64:
        base64_images.append((kf_b64, kf_mime))
        has_kf = True
        
    # 构建多模态指示指令，动态生成清晰的顺序解析说明
    instructions_parts = []
    current_idx = 1
    
    if num_char_refs > 0:
        if num_char_refs == 1:
            instructions_parts.append(f"Image {current_idx} is the character reference to preserve the character's face and style.")
        else:
            instructions_parts.append(f"Images {current_idx} to {current_idx + num_char_refs - 1} are character references to preserve the characters' faces and styles.")
        current_idx += num_char_refs
        
    if num_scene_refs > 0:
        if num_scene_refs == 1:
            instructions_parts.append(f"Image {current_idx} is the scene reference to preserve the background style and environment.")
        else:
            instructions_parts.append(f"Images {current_idx} to {current_idx + num_scene_refs - 1} are scene references to preserve the background style and environments.")
        current_idx += num_scene_refs
        
    if has_kf:
        instructions_parts.append(f"Image {current_idx} is the original frame composition reference to preserve the camera angle, layout, and pose.")
    
    instructions = " ".join(instructions_parts) + " " if instructions_parts else ""
    full_prompt = f"{instructions}Prompt: {prompt}"
    
    logger.info(f"镜号 #{shot_id}: 正在生成新{frame_label} (已注入 {len(base64_images)} 张参考图，其中角色图 {num_char_refs} 张，场景图 {num_scene_refs} 张)...")
    img_url = generate_image_via_gpt_image_2(api_key, base_url, full_prompt, base64_images)
    if img_url:
        download_image(img_url, save_path)
        time.sleep(1.5)
    else:
        logger.error(f"镜号 #{shot_id}: {frame_label}生图请求失败。")

def main():
    parser = argparse.ArgumentParser(description="调用 gpt-image-2 自动生成并下载分镜所需的所有首尾帧和视觉资产图")
    parser.add_argument("--api-key", help="t8star API Key")
    parser.add_argument("--base-url", default="https://ai.t8star.org/v1", help="API 的 baseurl 路径")
    parser.add_argument("--csv-input", default=DEFAULT_STORYBOARD_CSV, help="分镜 CSV 路径")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="输出目录")
    parser.add_argument("--assets-dir", default="assets", help="生成的资产图片保存的目录")
    parser.add_argument("--skip-existing", type=bool, default=True, help="是否跳过本地已存在的图片")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("T8STAR_API_KEY") or "sk-HZ6UTcRmzWCPue0W3S9JL6YN67h0OilXgIHFPxZWunGWfBDr"
    if not api_key:
        logger.error("缺少 API Key，请在根目录 .env 文件中配置 T8STAR_API_KEY。")
        sys.exit(1)

    csv_path = os.path.abspath(args.csv_input)
    output_dir = os.path.abspath(args.output_dir)
    assets_dir = os.path.abspath(args.assets_dir)
    
    os.makedirs(assets_dir, exist_ok=True)

    logger.info("=" * 60)
    logger.info("  videoMVP 自动生图流程启动 (Model: gpt-image-2)  ".center(60))
    logger.info("=" * 60)
    logger.info(f"读取分镜表: {csv_path}")
    logger.info(f"图片保存目录: {assets_dir}")

    # ================= 阶段 1: 生成核心资产参考图 =================
    logger.info("\n--- [阶段 1] 自动生成核心视觉资产参考图 ---")
    assets_meta_path = os.path.join(output_dir, "assets_metadata.json")
    asset_prompts_path = os.path.join(output_dir, "asset_prompts.md")
    
    if os.path.exists(assets_meta_path) and os.path.exists(asset_prompts_path):
        try:
            with open(assets_meta_path, "r", encoding="utf-8") as f_meta:
                assets_meta = json.load(f_meta)
            
            # 解析提示词
            asset_prompts = parse_asset_prompts(asset_prompts_path)
            
            # 合并人物和场景
            all_assets = {}
            all_assets.update(assets_meta.get("characters", {}))
            all_assets.update(assets_meta.get("scenes", {}))
            
            for asset_name, relative_path in all_assets.items():
                target_path = os.path.join(os.path.dirname(output_dir), relative_path)
                
                # 检查是否存在
                if args.skip_existing and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                    logger.info(f"资产 [{asset_name}] 本地已存在，跳过生成。")
                    continue
                    
                # 寻找提示词
                prompt = asset_prompts.get(asset_name)
                if not prompt:
                    # 尝试模糊匹配键名
                    for k, p in asset_prompts.items():
                        if asset_name in k or k in asset_name:
                            prompt = p
                            break
                            
                if not prompt:
                    logger.warning(f"未找到资产 [{asset_name}] 的提示词，跳过生成。")
                    continue
                    
                logger.info(f"正在生成资产 [{asset_name}] 的参考图...")
                img_url = generate_image_via_gpt_image_2(api_key, args.base_url, prompt)
                if img_url:
                    download_image(img_url, target_path)
                    time.sleep(1.5)  # 避免请求过快
                else:
                    logger.error(f"资产 [{asset_name}] 生图请求失败。")
        except Exception as e:
            logger.error(f"生成核心资产图片失败: {e}")
    else:
        logger.info("未检测到 assets_metadata.json 或 asset_prompts.md，跳过资产生成。")

    # ================= 阶段 2: 逐镜生成首尾帧 =================
    logger.info("\n--- [阶段 2] 逐镜生成分镜首尾帧图 ---")
    if not os.path.exists(csv_path):
        logger.error(f"未找到分镜 CSV 文件: {csv_path}，生图终止。")
        sys.exit(1)
        
    script_records = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            script_records.append(row)

    logger.info(f"共加载到 {len(script_records)} 个分镜，开始逐镜处理...")
    
    # 载入 assets_metadata.json
    assets_meta = {}
    if os.path.exists(assets_meta_path):
        try:
            with open(assets_meta_path, "r", encoding="utf-8") as f_meta:
                assets_meta = json.load(f_meta)
        except Exception as e:
            logger.error(f"读取 assets_metadata.json 失败: {e}")

    project_root = os.path.dirname(output_dir)
    keyframes_dir = os.path.join(output_dir, "keyframes")

    for row in script_records:
        shot_id = row["镜号"]
        is_end_frame = row.get("是否需要尾帧", "否")
        first_prompt = row.get("新首帧生图提示词", "")
        end_prompt = row.get("新尾帧生图提示词", "")
        
        # 1. 匹配对应的角色与场景资产图列表
        char_ref_paths = get_character_ref_paths(row, assets_meta, project_root)
        scene_ref_paths = get_scene_ref_paths(row, assets_meta, project_root)
        if char_ref_paths or scene_ref_paths:
            logger.info(f"镜号 #{shot_id}: 匹配到资产参考图 - 角色: {char_ref_paths}, 场景: {scene_ref_paths}")
        
        # 2. 处理首帧
        first_img_name = f"Scene-{shot_id}_first.png"
        first_img_path = os.path.join(assets_dir, first_img_name)
        kf_first_path = get_first_keyframe_path(keyframes_dir, shot_id)
        
        process_and_generate_frame(
            shot_id=shot_id,
            prompt=first_prompt,
            frame_type="first",
            keyframe_path=kf_first_path,
            char_ref_paths=char_ref_paths,
            scene_ref_paths=scene_ref_paths,
            api_key=api_key,
            base_url=args.base_url,
            save_path=first_img_path,
            skip_existing=args.skip_existing
        )
        
        # 3. 处理尾帧
        if is_end_frame == "是":
            end_img_name = f"Scene-{shot_id}_last.png"
            end_img_path = os.path.join(assets_dir, end_img_name)
            kf_last_path = get_last_keyframe_path(keyframes_dir, shot_id)
            
            process_and_generate_frame(
                shot_id=shot_id,
                prompt=end_prompt,
                frame_type="last",
                keyframe_path=kf_last_path,
                char_ref_paths=char_ref_paths,
                scene_ref_paths=scene_ref_paths,
                api_key=api_key,
                base_url=args.base_url,
                save_path=end_img_path,
                skip_existing=args.skip_existing
            )

    logger.info("=" * 60)
    logger.info("  所有首尾帧图像生成下载完成！  ".center(60))
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
