# -*- coding: utf-8 -*-
"""
脚本名称: split_video.py
描述: 
    基于 PySceneDetect 库（使用自适应检测器 AdaptiveDetector）对输入视频进行镜头检测，
    自动识别镜头的切换点，并调用 FFmpeg 对视频进行物理切分，保存为独立的视频片段。
输入:
    - 视频文件（路径在脚本中配置为 INPUT_VIDEO）
输出:
    - 镜头检测列表（控制台输出各镜头起止时间）
    - 切分后的视频片段（保存至 OUTPUT_DIR 目录）
"""
import os
import sys
# 动态添加项目根目录到 sys.path，支持在任意目录下运行该脚本
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scenedetect import detect, AdaptiveDetector, split_video_ffmpeg

from core.config import DEFAULT_INPUT_VIDEO, DEFAULT_OUTPUT_SCENES_DIR
from core.utils import get_logger

logger = get_logger("split_video")

# 配置输入和输出路径
INPUT_VIDEO = DEFAULT_INPUT_VIDEO
OUTPUT_DIR = DEFAULT_OUTPUT_SCENES_DIR

def split_shots():
    # 检查输入视频是否存在
    if not os.path.exists(INPUT_VIDEO):
        logger.error(f"输入视频文件不存在: {INPUT_VIDEO}")
        sys.exit(1)

    # 确保输出目录存在
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        logger.info(f"创建输出目录: {OUTPUT_DIR}")

    logger.info(f"开始分析视频镜头: {INPUT_VIDEO} ...")
    
    try:
        # 使用 AdaptiveDetector 进行高精度镜头检测
        # min_scene_len 默认为 0.6 秒 (在 30fps 下为 18 帧左右，此处用 15 帧)
        detector = AdaptiveDetector(min_scene_len=15)
        scene_list = detect(INPUT_VIDEO, detector)
        
        logger.info(f"镜头检测完成！共识别出 {len(scene_list)} 个镜头。")
        
        # 打印检测出来的镜头时间范围
        for i, scene in enumerate(scene_list):
            start_time = scene[0].get_timecode()
            end_time = scene[1].get_timecode()
            logger.info(f"  - 镜头 #{i+1:03d}: 从 {start_time} 到 {end_time}")
            
        # 物理分切视频
        if len(scene_list) > 0:
            logger.info(f"正在调用 FFmpeg 进行物理切分视频，请稍候...")
            split_video_ffmpeg(INPUT_VIDEO, scene_list, output_dir=OUTPUT_DIR, show_progress=True)
            logger.info(f"视频分切完成！片段已全部保存至: {OUTPUT_DIR}")
        else:
            logger.warning("未检测到任何明显的镜头切换点，未执行视频切割。")
            
    except Exception as e:
        logger.error(f"运行镜头分切时发生错误: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    split_shots()
