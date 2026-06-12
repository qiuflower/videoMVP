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
import json

# 动态添加项目根目录到 sys.path，支持在任意目录下运行该脚本
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import DEFAULT_STORYBOARD_CSV, DEFAULT_OUTPUT_DIR, DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_API_KEY
from core.llm_client import call_t8star_llm
from core.utils import clean_json_response, get_logger, resolve_asset_paths

logger = get_logger("video_prompts")

def build_frame_prompt(scale, target_char, content, scene, focal_length, camera_direction, visual_style):
    """
    根据人物/场景参考图与原视频构图构建高一致性的单帧生图提示词，避免冗余的细节描述导致一致性偏差
    """
    # 动态匹配参考图的引导指代
    has_char = target_char and target_char not in ["无", "无人物", "自适应", "默认风格"]
    has_scene = scene and scene not in ["无", "自适应", "默认风格"]
    
    ref_parts = []
    if has_char:
        ref_parts.append("人物参考图")
    if has_scene:
        ref_parts.append("场景参考图")
        
    ref_str = "和".join(ref_parts)
    prefix = f"根据提供的{ref_str}，" if ref_str else ""
    
    char_part = f"角色为：{target_char}，" if has_char else ""
    scene_part = f"场景为：{scene}，" if has_scene else ""
    
    return (
        f"{prefix}生成一幅电影感 {scale} 镜头。{char_part}{scene_part}画面具体动作与内容为：【{content}】。 "
        f"请严格继承并保持参考图中的人物容貌、服饰发型、色彩基调以及场景的视觉风格，确保画面高度一致。 "
        f"镜头参数：{focal_length}，{camera_direction}。画面风格：{visual_style}。 "
        f"Realistic photograph, high-resolution details, cinematic lighting. --ar 16:9 --no watermarks, signatures, text"
    )

def main():
    default_csv = DEFAULT_STORYBOARD_CSV
    if not os.path.exists(default_csv):
        fallback_csv = os.path.join(DEFAULT_OUTPUT_DIR, "new_script.csv")
        if os.path.exists(fallback_csv):
            default_csv = fallback_csv

    parser = argparse.ArgumentParser(description="根据原镜头参数与新剧本生成符合严格模板的视频重绘提示词")
    parser.add_argument("--csv-input", default=default_csv, help="主分镜 CSV 路径")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="输出目录")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="t8star API Key")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API 的 baseurl 路径")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="调用的模型名称")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("T8STAR_API_KEY") or os.environ.get("OPENAI_API_KEY")

    csv_path = os.path.abspath(args.csv_input)
    if not os.path.exists(csv_path):
        logger.error(f"未找到主分镜 CSV 文件: {csv_path}")
        sys.exit(1)

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # 加载视觉资产元数据配置，用于在此阶段动态解析绑定
    assets_meta_path = os.path.join(output_dir, "assets_metadata.json")
    assets_meta = {"characters": {}, "scenes": {}}
    if os.path.exists(assets_meta_path):
        try:
            with open(assets_meta_path, "r", encoding="utf-8") as f_meta:
                assets_meta = json.load(f_meta)
            logger.info("成功加载资产路径元数据配置。")
        except Exception as e:
            logger.warning(f"无法加载 assets_metadata.json: {e}")

    # 加载 LLM 智能资产绑定数据（由 bind_assets.py 生成）
    asset_bindings_path = os.path.join(output_dir, "asset_bindings.json")
    asset_bindings = {}
    if os.path.exists(asset_bindings_path):
        try:
            with open(asset_bindings_path, "r", encoding="utf-8") as f_bind:
                asset_bindings = json.load(f_bind)
            logger.info(f"成功加载 LLM 资产绑定数据，共 {len(asset_bindings)} 个镜头。")
        except Exception as e:
            logger.warning(f"无法加载 asset_bindings.json: {e}，将回退到规则匹配。")

    # 加载统一的提示词生成模板 (decoupled_prompts_prompt.txt)
    decoupled_prompt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "decoupled_prompts_prompt.txt")
    decoupled_template = ""
    if os.path.exists(decoupled_prompt_path):
        try:
            with open(decoupled_prompt_path, "r", encoding="utf-8") as f_p:
                decoupled_template = f_p.read()
            logger.info("成功载入解耦提示词模板。")
        except Exception as e:
            logger.warning(f"无法载入 decoupled_prompts_prompt.txt: {e}")

    # 读取分镜与新剧本数据
    script_records = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            script_records.append(row)

    logger.info(f"成功读取到 {len(script_records)} 个镜头剧本。")
    logger.info("正在进行视觉资产解析绑定并生成视频重绘提示词 (Video Redraw Prompts)...")

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
        
        # 尾帧评估数据
        is_end_frame = r.get("是否需要尾帧", "否")
        end_frame_desc = r.get("尾帧画面描述", "无")
        
        # 5要素额外字段
        new_scene = r.get("新场景", "")
        focal_length = r.get("新焦段", "自适应")
        camera_direction = r.get("新镜头方位", "自适应")
        visual_style = r.get("新画面风格", "默认风格")

        # 判定参考人像角色
        target_char = r.get("参考角色", "").strip()
        if not target_char:
            # 尝试从 assets_meta 获取实际角色名称进行动态匹配
            chars_list = list(assets_meta.get("characters", {}).keys())
            if chars_list:
                primary_char = chars_list[0]
                secondary_char = chars_list[1] if len(chars_list) > 1 else None
                target_char = primary_char
                if secondary_char:
                    sec_kws = ["老师", "周伯", "老园丁", "陈教授", "老钟表匠", "教师", "园艺师", "老者", "长者"]
                    pri_kws = ["女孩", "林夏", "林禾", "林艾", "主角", "我"]
                    has_pri = any(k in new_content for k in pri_kws)
                    has_sec = any(k in new_content for k in sec_kws)
                    if has_pri and has_sec:
                        target_char = f"{primary_char}与{secondary_char}"
                    elif has_sec:
                        target_char = secondary_char
            else:
                target_char = "主角"

        # 1. 动态匹配角色参考图 — 优先使用 LLM 绑定结果
        matched_chars_links = []
        char_ref_path = "assets/character_ref.png"
        chars_dict = assets_meta.get("characters", {})
        shot_binding = asset_bindings.get(shot_id, {})

        if shot_binding and shot_binding.get("characters") and chars_dict:
            # 使用 LLM 绑定数据
            bound_char_names = shot_binding["characters"]
            bound_char_paths = []
            for cname in bound_char_names:
                if cname in chars_dict:
                    cpath = chars_dict[cname]
                    bound_char_paths.append(cpath)
                    matched_chars_links.append(f"[角色参考-{cname}]({cpath})")
            if bound_char_paths:
                char_ref_path = ",".join(bound_char_paths)
            else:
                # LLM 绑定的名称全部无效，兜底第一个角色
                first_name = list(chars_dict.keys())[0]
                first_path = list(chars_dict.values())[0]
                matched_chars_links.append(f"[角色参考-{first_name}]({first_path})")
                char_ref_path = first_path
        elif chars_dict:
            # 回退到旧的规则匹配
            char_paths, char_names = resolve_asset_paths(target_char, chars_dict, category="characters")
            if char_paths:
                char_ref_path = ",".join(char_paths)
                for name_key, path_val in zip(char_names, char_paths):
                    matched_chars_links.append(f"[角色参考-{name_key}]({path_val})")
            else:
                first_name = list(chars_dict.keys())[0]
                first_path = list(chars_dict.values())[0]
                matched_chars_links.append(f"[角色参考-{first_name}]({first_path})")
                char_ref_path = first_path
        else:
            matched_chars_links.append(f"[角色参考]({char_ref_path})")

        # 2. 动态匹配场景参考图 — 优先使用 LLM 绑定结果
        matched_scenes_links = []
        scene_ref_path = "assets/scene_ref.png"
        scenes_dict = assets_meta.get("scenes", {})

        if shot_binding and shot_binding.get("scenes") and scenes_dict:
            # 使用 LLM 绑定数据
            bound_scene_names = shot_binding["scenes"]
            bound_scene_paths = []
            for sname in bound_scene_names:
                if sname in scenes_dict:
                    spath = scenes_dict[sname]
                    bound_scene_paths.append(spath)
                    matched_scenes_links.append(f"[场景参考-{sname}]({spath})")
            if bound_scene_paths:
                scene_ref_path = ",".join(bound_scene_paths)
            else:
                first_name = list(scenes_dict.keys())[0]
                first_path = list(scenes_dict.values())[0]
                matched_scenes_links.append(f"[场景参考-{first_name}]({first_path})")
                scene_ref_path = first_path
        elif scenes_dict:
            # 回退到旧的规则匹配
            scene_paths, scene_names = resolve_asset_paths(new_scene, scenes_dict, category="scenes")
            if scene_paths:
                scene_ref_path = ",".join(scene_paths)
                for name_key, path_val in zip(scene_names, scene_paths):
                    matched_scenes_links.append(f"[场景参考-{name_key}]({path_val})")
            else:
                first_name = list(scenes_dict.keys())[0]
                first_path = list(scenes_dict.values())[0]
                matched_scenes_links.append(f"[场景参考-{first_name}]({first_path})")
                scene_ref_path = first_path
        else:
            matched_scenes_links.append(f"[场景参考]({scene_ref_path})")

        # 4个资产相关的基本字段
        orig_video_path = r.get("原视频路径", f"scenes/Scene-{shot_id}.mp4")
        redraw_video_path = r.get("重绘视频路径", f"generated/Scene-{shot_id}_redraw.mp4")

        # 编译首帧与尾帧的文生图/图生图提示词 (完全基于 GPTImage2 和 NanoBanana 规范)
        # 编译首帧与尾帧的生图提示词与视频重绘提示词
        has_llm_worked = False
        if api_key and decoupled_template:
            # 格式化 LLM prompt
            llm_prompt = decoupled_template \
                .replace("{shot_id}", shot_id) \
                .replace("{scale}", scale) \
                .replace("{movement}", movement) \
                .replace("{orig_content}", orig_content) \
                .replace("{new_content}", new_content) \
                .replace("{is_end_frame}", is_end_frame) \
                .replace("{end_frame_desc}", end_frame_desc) \
                .replace("{target_char}", target_char) \
                .replace("{new_scene}", new_scene) \
                .replace("{focal_length}", focal_length)
            
            try:
                logger.info(f"正在调用 LLM 生成 镜号 #{shot_id} 的解耦提示词...")
                response_text = call_t8star_llm(api_key, args.base_url, args.model, llm_prompt, temperature=0.3)
                if response_text:
                    cleaned_json = clean_json_response(response_text)
                    prompt_data = json.loads(cleaned_json)
                    first_frame_prompt = prompt_data.get("新首帧生图提示词", "").strip()
                    end_frame_prompt = prompt_data.get("新尾帧生图提示词", "").strip()
                    prompt = prompt_data.get("视频重绘提示词", "").strip()
                    if first_frame_prompt and prompt:
                        has_llm_worked = True
                        logger.info(f"镜号 #{shot_id} 提示词 LLM 生成成功！")
            except Exception as e:
                logger.error(f"调用 LLM 生成 镜号 #{shot_id} 提示词失败: {e}。执行规则兜底...")

        if not has_llm_worked:
            # 规则拼接兜底逻辑 (原逻辑)
            first_frame_prompt = build_frame_prompt(
                scale=scale,
                target_char=target_char,
                content=new_content,
                scene=new_scene,
                focal_length=focal_length,
                camera_direction=camera_direction,
                visual_style=visual_style
            )
            
            if is_end_frame == "是":
                end_frame_prompt = build_frame_prompt(
                    scale=scale,
                    target_char=target_char,
                    content=end_frame_desc,
                    scene=new_scene,
                    focal_length=focal_length,
                    camera_direction=camera_direction,
                    visual_style=visual_style
                )
            else:
                end_frame_prompt = "无"

            dialogue_part = f"新台词/旁白为：【{dialogue}】。" if dialogue and dialogue.strip() not in ["", "无"] else ""
            audio_part = f"新音效为：【{audio}】。" if audio and audio.strip() not in ["", "无", "无音效"] else ""
            
            extra_parts = []
            if dialogue_part:
                extra_parts.append(dialogue_part)
            if audio_part:
                extra_parts.append(audio_part)
            if duration:
                extra_parts.append(f"时长为 {duration}秒。")
                
            extra_str = "".join(extra_parts)
            if extra_str:
                extra_str = f"同时结合：{extra_str}"
            else:
                extra_str = ""

            prompt = (
                f"输入：原镜头视频、新首帧图片、以及资产参考图（角色为：{target_char}，场景为：{new_scene}）。"
                f"要求：继承新首帧的构图与人物姿态，保持原片视频的运动（{movement}）和节奏，"
                f"仅将人物替换为资产图角色，场景替换为资产图场景，并将画面调整为新焦段（{focal_length}）的镜头感觉。"
            )
            if extra_str:
                prompt += f" {extra_str}"

        # 整合并重构超链接列，包含原片、重绘视频以及匹配到的全部视觉资产链接
        all_links = [
            f"[原片视频]({orig_video_path})", 
            f"[重绘视频]({redraw_video_path})"
        ] + matched_chars_links + matched_scenes_links
        related_links = ", ".join(all_links)

        # 提取实际绑定的资产名称（用于新增的「调用资产」列）
        bound_char_names = [link.split("-", 1)[1].split("]")[0] for link in matched_chars_links if "-" in link]
        bound_scene_names = [link.split("-", 1)[1].split("]")[0] for link in matched_scenes_links if "-" in link]
        bound_chars_str = "、".join(bound_char_names) if bound_char_names else "无"
        bound_scenes_str = "、".join(bound_scene_names) if bound_scene_names else "无"

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
            "新场景": new_scene,
            "新焦段": focal_length,
            "新镜头方位": camera_direction,
            "新画面风格": visual_style,
            "新台词/旁白": dialogue,
            "新音效/音乐": audio,
            "是否需要尾帧": is_end_frame,
            "尾帧画面描述": end_frame_desc,
            "新首帧生图提示词": first_frame_prompt,
            "新尾帧生图提示词": end_frame_prompt,
            "视频重绘提示词": prompt,
            "预览图": preview,
            "原视频路径": orig_video_path,
            "角色参考图路径": char_ref_path,
            "场景参考图路径": scene_ref_path,
            "重绘视频路径": redraw_video_path,
            "相关链接": related_links,
            "绑定角色资产": bound_chars_str,
            "绑定场景资产": bound_scenes_str
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
    
    # 动态加载资产元数据并编译为 Markdown 表格插入到文件头部
    assets_meta_path = os.path.join(output_dir, "assets_metadata.json")
    assets_markdown = ""
    if os.path.exists(assets_meta_path):
        try:
            with open(assets_meta_path, "r", encoding="utf-8") as f_meta:
                assets_meta = json.load(f_meta)
            assets_rows = []
            for name, path in assets_meta.get("characters", {}).items():
                assets_rows.append(f"| 角色人物 | {name} | <img src=\"../{path}\" width=\"80\" /> | `{path}` |")
            for name, path in assets_meta.get("scenes", {}).items():
                assets_rows.append(f"| 场景风格 | {name} | <img src=\"../{path}\" width=\"80\" /> | `{path}` |")
            if assets_rows:
                assets_markdown = (
                    "## 🎨 核心视觉资产参考 (Core Visual Assets)\n\n"
                    "本分镜剧本使用以下核心视觉资产参考图进行人物与场景的一致性锁定：\n\n"
                    "| 资产类型 | 资产名称 | 预览图 | 本地参考路径 |\n"
                    "| --- | --- | --- | --- |\n"
                    + "\n".join(assets_rows) + "\n\n---\n\n"
                )
        except Exception as e:
            pass

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {story_title} —— 视频分镜剧本\n\n")
        f.write("此分镜剧本基于原视频节奏，由大语言模型重构，保持了镜头规格、运镜和时长 100% 对应。\n\n")
        if assets_markdown:
            f.write(assets_markdown)
        f.write("| 镜号 | 镜头预览 | 镜头参数 | 原片分镜参考 | 全新创意剧本 | 调用资产 | 新首帧图像 | 新尾帧图像 | 相关链接 | 视频重绘提示词 |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for rec in prompt_records:
            img_md = f"<img src=\"{rec['预览图']}\" width=\"120\" style=\"min-width: 120px;\" />" if rec['预览图'] else "无"
            
            # 镜头参数 (保持精简)
            param_str = (
                f"景别：{rec['景别']}<br>"
                f"运镜：{rec['运动镜头']}<br>"
                f"时长：{rec['时长(秒)']}秒"
            )
            
            # 原片分镜参考
            orig_content_clean = rec['原画面内容'].replace("\n", "<br>")
            orig_dialogue_clean = rec['原台词/旁白'].replace("\n", "<br>")
            orig_audio_clean = rec['原音效/音乐'].replace("\n", "<br>")
            ref_str = f"【画面内容】{orig_content_clean}<br>【台词/旁白】{orig_dialogue_clean}<br>【音效/音乐】{orig_audio_clean}"
            
            # 全新创意剧本 (保持精炼)
            new_content_clean = rec['新画面内容'].replace("\n", "<br>")
            char_clean = rec['参考角色'].replace("\n", "<br>")
            scene_clean = rec.get('新场景', '').replace("\n", "<br>")
            focal_clean = rec.get('新焦段', '').replace("\n", "<br>")
            cam_clean = rec.get('新镜头方位', '').replace("\n", "<br>")
            style_clean = rec.get('新画面风格', '').replace("\n", "<br>")
            new_dialogue_clean = rec['新台词/旁白'].replace("\n", "<br>")
            new_audio_clean = rec['新音效/音乐'].replace("\n", "<br>")
            script_str = (
                f"【新画面】{new_content_clean}<br>"
                f"【角色】{char_clean}<br>"
                f"【新场景】{scene_clean}<br>"
                f"【新焦段】{focal_clean}<br>"
                f"【镜头方位】{cam_clean}<br>"
                f"【画面风格】{style_clean}<br>"
                f"【新台词】{new_dialogue_clean}<br>"
                f"【新音效】{new_audio_clean}"
            )
            
            # 新首尾帧生图预览与提示词，使用 img 标签控制显示宽度与最小宽度，防止被表格挤压
            first_frame_path = f"assets/Scene-{rec['镜号']}_first.png"
            first_img_md = f"<img src=\"../{first_frame_path}\" width=\"120\" style=\"min-width: 120px;\" /><br>**首帧提示词**：<br>`{rec['新首帧生图提示词']}`"
            
            if rec.get('是否需要尾帧', '否') == '是':
                end_frame_path = f"assets/Scene-{rec['镜号']}_last.png"
                end_img_md = f"<img src=\"../{end_frame_path}\" width=\"80\" style=\"min-width: 80px;\" /><br>**尾帧提示词**：<br>`{rec['新尾帧生图提示词']}`"
            else:
                end_img_md = "无（AI评估无需尾帧）"

            # 独立的相关链接呈现，以换行分割，调整相对路径以适应 output/ 子目录下的 storyboard.md
            links_str = rec['相关链接']
            import re
            links_str = re.sub(r'\((assets|generated)/', r'(../\1/', links_str)
            links_str = links_str.replace(", ", "<br>")
            links_html = f"<div style=\"min-width: 120px;\">{links_str}</div>"
            
            prompt_clean = rec['视频重绘提示词'].replace("\n", "<br>")

            # 调用资产列
            asset_str = f"**角色**：{rec['绑定角色资产']}<br>**场景**：{rec['绑定场景资产']}"
            
            f.write(f"| {rec['镜号']} | {img_md} | {param_str} | {ref_str} | {script_str} | {asset_str} | {first_img_md} | {end_img_md} | {links_html} | {prompt_clean} |\n")

    # 2. 导出/覆写主分镜 CSV 文件
    csv_path_out = os.path.join(output_dir, "storyboard.csv")
    csv_headers = [
        "镜号", "景别", "运动镜头", "时长(秒)", 
        "原画面内容", "原台词/旁白", "原音效/音乐",
        "新画面内容", "参考角色", "新场景", "新焦段", "新镜头方位", "新画面风格",
        "新台词/旁白", "新音效/音乐", "是否需要尾帧", "尾帧画面描述",
        "新首帧生图提示词", "新尾帧生图提示词", "预览图", 
        "原视频路径", "角色参考图路径", "场景参考图路径", "重绘视频路径", "相关链接",
        "绑定角色资产", "绑定场景资产",
        "视频重绘提示词"
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
                rec["新场景"],
                rec["新焦段"],
                rec["新镜头方位"],
                rec["新画面风格"],
                rec["新台词/旁白"],
                rec["新音效/音乐"],
                rec.get("是否需要尾帧", "否"),
                rec.get("尾帧画面描述", "无"),
                rec.get("新首帧生图提示词", "无"),
                rec.get("新尾帧生图提示词", "无"),
                rec["预览图"],
                rec["原视频路径"],
                rec["角色参考图路径"],
                rec["场景参考图路径"],
                rec["重绘视频路径"],
                rec["相关链接"],
                rec["绑定角色资产"],
                rec["绑定场景资产"],
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
