# -*- coding: utf-8 -*-
import os

# 项目根目录 (videoMVP 根路径)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_dotenv(dotenv_path):
    """手动解析并加载 .env 文件中的环境变量"""
    if os.path.exists(dotenv_path):
        try:
            with open(dotenv_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        os.environ[key] = val
        except Exception as e:
            print(f"[Warning] 加载 env 文件出错: {e}")

# 自动加载环境变量 (优先项目根目录，其次当前工作目录)
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv(".env")

# 统一的全局路径配置契约
DEFAULT_INPUT_VIDEO = os.path.join(BASE_DIR, "video", "1275065186-1-192.mp4")
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DEFAULT_OUTPUT_SCENES_DIR = os.path.join(DEFAULT_OUTPUT_DIR, "scenes")
DEFAULT_STORYBOARD_CSV = os.path.join(DEFAULT_OUTPUT_DIR, "storyboard.csv")
