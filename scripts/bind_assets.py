# -*- coding: utf-8 -*-
"""
脚本名称: bind_assets.py
描述: 
    使用大模型 API 智能判断每个镜头应该绑定哪些角色和场景资产。
    替代原先基于字符重合的规则匹配（resolve_asset_paths），实现精准的语义级资产绑定。
    
输入:
    - storyboard.csv: 包含每个镜头的"参考角色"和"新场景"描述
    - assets_metadata.json: 包含所有可用的角色和场景资产名称及路径

输出:
    - asset_bindings.json: 每个镜号对应绑定的角色资产名称列表和场景资产名称列表
"""
import os
import sys
import csv
import json
import argparse

# 动态添加项目根目录到 sys.path，支持在任意目录下运行该脚本
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import DEFAULT_OUTPUT_DIR, DEFAULT_STORYBOARD_CSV, DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_API_KEY
from core.llm_client import call_t8star_llm
from core.utils import clean_json_response, get_logger

logger = get_logger("bind_assets")


def load_prompt_template():
    """加载资产绑定提示词模板"""
    prompt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "asset_binding_prompt.txt")
    if not os.path.exists(prompt_path):
        logger.error(f"未找到资产绑定提示词模板: {prompt_path}")
        sys.exit(1)
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def build_shots_summary(csv_path):
    """从 CSV 中提取每个镜头的关键信息，用于发送给大模型"""
    shots = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            shot_id = row.get("镜号", "")
            ref_char = row.get("参考角色", "").strip()
            new_scene = row.get("新场景", "").strip()
            new_content = row.get("新画面内容", "").strip()
            shots.append({
                "镜号": shot_id,
                "参考角色": ref_char,
                "新场景": new_scene,
                "新画面内容": new_content
            })
    return shots


def main():
    parser = argparse.ArgumentParser(description="使用大模型 API 智能绑定每镜资产")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API Key")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="调用的模型名称")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API 的 baseurl 路径")
    parser.add_argument("--csv-input", default=DEFAULT_STORYBOARD_CSV, help="主分镜 CSV 路径")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="输出目录")
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

    # 1. 加载资产元数据
    assets_meta_path = os.path.join(output_dir, "assets_metadata.json")
    if not os.path.exists(assets_meta_path):
        logger.error(f"未找到资产元数据文件: {assets_meta_path}，请先运行 extract_assets.py")
        sys.exit(1)

    with open(assets_meta_path, "r", encoding="utf-8") as f:
        assets_meta = json.load(f)

    characters = assets_meta.get("characters", {})
    scenes = assets_meta.get("scenes", {})

    if not characters and not scenes:
        logger.warning("资产元数据中无角色和场景，无需绑定。")
        sys.exit(0)

    # 2. 提取镜头摘要
    shots = build_shots_summary(csv_path)
    logger.info(f"共加载 {len(shots)} 个镜头数据。")

    # 3. 构建大模型提示词
    template = load_prompt_template()

    characters_list = "\n".join(f"- {name}" for name in characters.keys())
    scenes_list = "\n".join(f"- {name}" for name in scenes.keys())
    shots_data = "\n".join(
        f"- 镜号 {s['镜号']}: 参考角色=[{s['参考角色']}], 新场景=[{s['新场景']}], 画面内容=[{s['新画面内容'][:80]}]"
        for s in shots
    )

    prompt = template \
        .replace("{characters_list}", characters_list) \
        .replace("{scenes_list}", scenes_list) \
        .replace("{shots_data}", shots_data)

    # 4. 调用大模型
    logger.info("正在调用大模型进行智能资产绑定（一次性处理全部镜头）...")
    response_text = call_t8star_llm(api_key, args.base_url, args.model, prompt, temperature=0.2)

    if not response_text:
        logger.error("API 未返回资产绑定结果。")
        sys.exit(1)

    # 5. 解析结果
    cleaned_json = clean_json_response(response_text)
    try:
        data = json.loads(cleaned_json)
        bindings = data.get("bindings", data)

        # 验证绑定结果的有效性
        valid_char_names = set(characters.keys())
        valid_scene_names = set(scenes.keys())
        validated_bindings = {}

        for shot_id, binding in bindings.items():
            bound_chars = binding.get("characters", [])
            bound_scenes = binding.get("scenes", [])

            # 过滤掉不存在的资产名称
            valid_chars = [c for c in bound_chars if c in valid_char_names]
            valid_scenes = [s for s in bound_scenes if s in valid_scene_names]

            if len(valid_chars) != len(bound_chars):
                invalid = set(bound_chars) - valid_char_names
                logger.warning(f"镜号 {shot_id}: 大模型返回了不存在的角色资产 {invalid}，已自动过滤。")

            if len(valid_scenes) != len(bound_scenes):
                invalid = set(bound_scenes) - valid_scene_names
                logger.warning(f"镜号 {shot_id}: 大模型返回了不存在的场景资产 {invalid}，已自动过滤。")

            validated_bindings[shot_id] = {
                "characters": valid_chars,
                "scenes": valid_scenes
            }

        # 6. 输出统计
        total_shots = len(validated_bindings)
        avg_chars = sum(len(b["characters"]) for b in validated_bindings.values()) / max(total_shots, 1)
        avg_scenes = sum(len(b["scenes"]) for b in validated_bindings.values()) / max(total_shots, 1)
        logger.info(f"绑定完成: {total_shots} 个镜头，平均每镜绑定 {avg_chars:.1f} 个角色、{avg_scenes:.1f} 个场景。")

        # 7. 保存绑定结果
        bindings_path = os.path.join(output_dir, "asset_bindings.json")
        with open(bindings_path, "w", encoding="utf-8") as f:
            json.dump(validated_bindings, f, ensure_ascii=False, indent=2)
        logger.info(f"资产绑定结果已保存至: {bindings_path}")

        # 打印前几个绑定供人工检查
        logger.info("--- 绑定结果预览（前 5 镜）---")
        for shot_id in sorted(validated_bindings.keys())[:5]:
            b = validated_bindings[shot_id]
            logger.info(f"  镜号 {shot_id}: 角色={b['characters']}, 场景={b['scenes']}")

    except Exception as e:
        logger.error(f"解析资产绑定 JSON 失败: {e}。原始返回文本:\n{response_text[:500]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
