# -*- coding: utf-8 -*-
"""
脚本名称: verify_assets.py
描述: 
    自动验证项目中的视觉资产完整性与分镜绑定准确度。
    1. 检查 assets_metadata.json 中登记的资产文件是否真实存在于本地，且大小正常。
    2. 遍历 storyboard.csv 中的所有分镜，模拟 resolve_asset_paths 匹配逻辑，
       如果某镜的“参考角色”或“新场景”无法匹配到任何有效资产而被迫使用兜底参考，则抛出警告。
"""
import os
import sys
import csv
import json

# 动态添加项目根目录到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import DEFAULT_STORYBOARD_CSV, DEFAULT_OUTPUT_DIR
from core.utils import get_logger, resolve_asset_paths

logger = get_logger("verify_assets")

def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = DEFAULT_OUTPUT_DIR
    csv_path = DEFAULT_STORYBOARD_CSV

    logger.info("=" * 60)
    logger.info("  videoMVP 资产完整性与准确度校验启动  ".center(60))
    logger.info("=" * 60)

    # 1. 检查 assets_metadata.json
    assets_meta_path = os.path.join(output_dir, "assets_metadata.json")
    if not os.path.exists(assets_meta_path):
        logger.error(f"❌ 错误: 未找到资产元数据配置文件: {assets_meta_path}")
        return

    try:
        with open(assets_meta_path, "r", encoding="utf-8") as f:
            assets_meta = json.load(f)
    except Exception as e:
        logger.error(f"❌ 错误: 无法解析 assets_metadata.json: {e}")
        return

    characters = assets_meta.get("characters", {})
    scenes = assets_meta.get("scenes", {})

    logger.info(f"📊 资产库登记数据: 已登记角色数 {len(characters)} 个，场景风格数 {len(scenes)} 个。")

    # 2. 检查物理文件存在性
    missing_files = 0
    logger.info("\n--- [第 1 阶段] 检查资产库文件完整性 ---")
    for cat_name, cat_dict in [("角色人物", characters), ("场景风格", scenes)]:
        for name, path in cat_dict.items():
            full_path = os.path.join(project_root, path)
            if not os.path.exists(full_path):
                logger.error(f"❌ 缺失物理资产: [{cat_name}] {name} -> 预设路径不存在: {path}")
                missing_files += 1
            elif os.path.getsize(full_path) == 0:
                logger.warning(f"⚠️ 空资产文件: [{cat_name}] {name} -> 本地文件大小为 0: {path}")
                missing_files += 1
            else:
                logger.info(f"✅ 文件完整: [{cat_name}] {name} ({os.path.getsize(full_path) / 1024:.1f} KB)")

    if missing_files == 0:
        logger.info("🎉 第 1 阶段通过: 所有已登记资产物理文件完整存在。")
    else:
        logger.warning(f"⚠️ 警告: 第 1 阶段有 {missing_files} 个资产文件异常，请先运行 `generate_images.py` 生成物理图片。")

    # 3. 检查分镜映射的准确性
    if not os.path.exists(csv_path):
        logger.error(f"\n❌ 错误: 未找到分镜主 CSV 文件: {csv_path}，无法执行分镜对齐检查。")
        return

    logger.info("\n--- [第 2 阶段] 检查各分镜资产匹配准确性 ---")
    mismatch_count = 0
    total_shots = 0

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_shots += 1
            shot_id = row["镜号"]
            target_char = row.get("参考角色", "").strip()
            new_scene = row.get("新场景", "").strip()

            # 验证角色
            char_paths, char_names = resolve_asset_paths(target_char, characters, category="characters")
            if target_char and target_char not in ["无", "无人物", "自适应"]:
                if not char_paths:
                    logger.warning(f"⚠️ 镜号 #{shot_id}: 角色 '{target_char}' 未匹配到任何资产图片，将执行兜底绑定。")
                    mismatch_count += 1
                else:
                    logger.info(f"🔹 镜号 #{shot_id}: 角色 '{target_char}' -> 成功匹配到 {char_names}")

            # 验证场景
            scene_paths, scene_names = resolve_asset_paths(new_scene, scenes, category="scenes")
            if new_scene and new_scene not in ["无", "自适应"]:
                if not scene_paths:
                    logger.warning(f"⚠️ 镜号 #{shot_id}: 场景 '{new_scene}' 未匹配到任何资产图片，将执行兜底绑定。")
                    mismatch_count += 1
                else:
                    logger.info(f"🔹 镜号 #{shot_id}: 场景 '{new_scene}' -> 成功匹配到 {scene_names}")

    logger.info("\n" + "=" * 60)
    logger.info("  校验结果总结  ".center(60))
    logger.info("=" * 60)
    logger.info(f"总计检查分镜数: {total_shots} 镜")
    if mismatch_count == 0:
        logger.info("🎉 所有分镜引用的角色/场景资产均能完美且准确地定位，无兜底漂移情况发生！")
    else:
        logger.warning(f"⚠️ 共有 {mismatch_count} 处分镜资产匹配发生兜底，建议在 `assets_metadata.json` 中添加同义词，或修正 storyboard 中的角色/场景名称。")

if __name__ == "__main__":
    main()
