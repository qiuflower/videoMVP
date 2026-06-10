# -*- coding: utf-8 -*-
import os
import sys
import logging

def get_logger(name="videoMVP"):
    """
    获取或创建统一格式的 logger。
    配置根 logger (root) 同时输出到标准输出 (StreamHandler) 和根目录下 logs/app.log (FileHandler)。
    各模块 logger 会自动向上传递给根 logger。
    """
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        root_logger.setLevel(log_level)
        
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        try:
            from core.config import BASE_DIR
            log_dir = os.path.join(BASE_DIR, "logs")
        except ImportError:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
            
        try:
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "app.log")
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            # 无法创建日志文件时回退使用 print 报错
            print(f"[Warning] 无法创建日志文件处理器: {e}")
            
    return logging.getLogger(name)


def clean_json_response(content):
    """
    清理 JSON 字符串外层的 Markdown 标记（例如 ```json ... ```）。
    
    参数:
        content (str): 大模型返回的原始文本。
        
    返回:
        str: 清理后的纯 JSON 格式字符串。
    """
    if not content:
        return ""
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        # 移除开头的 ``` 或 ```json
        if lines[0].startswith("```"):
            lines = lines[1:]
        # 移除结尾的 ```
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    return content
