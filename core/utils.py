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


def resolve_asset_paths(target_string, assets_dict, category="characters"):
    """
    根据目标字符串（如角色名称或场景名称）与资产字典进行模糊/精确匹配，
    返回匹配到的资产物理路径列表与名称列表。
    """
    import re
    matched_paths = []
    matched_names = []
    
    if not target_string:
        return matched_paths, matched_names
        
    target_string = target_string.strip()
    if target_string in ["无", "无人物", "自适应", "默认风格", "待生成"]:
        return matched_paths, matched_names
        
    # 遍历 assets_dict 进行匹配
    for name_key, path_val in assets_dict.items():
        matched = False
        # 1. 提取核心中文字符集
        # 过滤掉一些常见辅助或连词中文字符，避免误判
        filter_chars = {"和", "与", "人", "的", "个", "主", "角", "在", "中", "里", "景", "处", "型", "化", "新"}
        common_chars = set(name_key) & set(target_string)
        common_chars = {c for c in common_chars if c not in filter_chars}
        
        # 2. 匹配规则：字符重合数大于等于2，或者一个是另一个的子串
        if len(common_chars) >= 2 or name_key in target_string or target_string in name_key:
            matched = True
        else:
            # 去除一些常见的前后缀后再做子串包含匹配
            core_name = name_key.replace("年轻女创业者", "").replace("老园丁", "")
            if core_name and core_name in target_string:
                matched = True
                
        if matched:
            if path_val not in matched_paths:
                matched_paths.append(path_val)
                matched_names.append(name_key)
                
    # 3. 常见角色名称兜底映射规则
    if not matched_paths and category == "characters":
        if any(k in target_string for k in ["主角", "女创业者", "林禾", "林艾"]):
            lin_he_path = assets_dict.get("年轻女创业者林禾")
            if lin_he_path:
                matched_paths.append(lin_he_path)
                matched_names.append("年轻女创业者林禾")
        if any(k in target_string for k in ["周伯", "老园丁", "老园丁周伯"]):
            zhou_bo_path = assets_dict.get("老园丁周伯")
            if zhou_bo_path:
                matched_paths.append(zhou_bo_path)
                matched_names.append("老园丁周伯")
                
    return matched_paths, matched_names

