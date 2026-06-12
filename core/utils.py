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
        
    # 1. 遍历 assets_dict 进行精确和字符重合匹配
    for name_key, path_val in assets_dict.items():
        matched = False
        # 提取核心中文字符集，过滤常见连词或辅助词
        filter_chars = {"和", "与", "人", "的", "个", "主", "角", "在", "中", "里", "景", "处", "型", "化", "新"}
        common_chars = set(name_key) & set(target_string)
        common_chars = {c for c in common_chars if c not in filter_chars}
        
        # 匹配规则：字符重合数大于等于2，或者一个是另一个的子串
        if len(common_chars) >= 2 or name_key in target_string or target_string in name_key:
            matched = True
        else:
            # 去除一些常见的前后缀后再做子串包含匹配
            core_name = name_key.replace("年轻女创业者", "").replace("老园丁", "").replace("年轻植物插画女孩", "").replace("银发园艺师", "")
            if core_name and core_name in target_string:
                matched = True
                
        if matched:
            if path_val not in matched_paths:
                matched_paths.append(path_val)
                matched_names.append(name_key)

    # 2. 动态角色/场景的兜底及近义词映射规则 (不限制 'if not matched_paths'，以支持多角色同时匹配)
    if category == "characters":
        # 检查是否包含主角或主角近义词
        has_protagonist = any(k in target_string for k in ["主角", "女孩", "林夏", "林禾", "林艾", "修复师", "插画师", "修船匠", "母亲"])
        # 检查是否包含导师/长者近义词
        has_elder = any(k in target_string for k in ["园艺师", "老师", "老园丁", "老钟表匠", "周伯", "陈教授", "老教师", "老者", "长者"])
        # 检查是否包含特定配角（母亲、妹妹/童年玩伴）
        has_mother_specific = "母亲" in target_string
        has_sister_specific = any(k in target_string for k in ["妹妹", "童年玩伴", "玩伴"])

        # 如果包含主角，并且还没有匹配到主角
        if has_protagonist:
            proto_key = None
            for name_key in assets_dict.keys():
                if any(k in name_key for k in ["女孩", "林夏", "林禾", "林艾", "创业者", "修复师", "主角"]):
                    proto_key = name_key
                    break
            if not proto_key and assets_dict:
                proto_key = list(assets_dict.keys())[0]
            if proto_key and proto_key not in matched_names:
                matched_paths.append(assets_dict[proto_key])
                matched_names.append(proto_key)

        # 如果包含导师/长者，并且还没有匹配到该长者
        if has_elder:
            elder_key = None
            for name_key in assets_dict.keys():
                if any(k in name_key for k in ["老师", "周伯", "老园丁", "陈教授", "老钟表匠", "教师", "园艺师", "老者", "长者"]):
                    elder_key = name_key
                    break
            if not elder_key and len(assets_dict) > 1:
                # 寻找不是主角的那个作为兜底
                other_keys = [k for k in assets_dict.keys() if k not in matched_names]
                if other_keys:
                    elder_key = other_keys[0]
            if elder_key and elder_key not in matched_names:
                matched_paths.append(assets_dict[elder_key])
                matched_names.append(elder_key)

        # 如果包含母亲，但在 assets_dict 中找不到包含“母亲”的键，尝试模糊匹配“母亲”或“妈妈”的资产
        if has_mother_specific:
            mother_key = None
            for name_key in assets_dict.keys():
                if "母亲" in name_key or "妈妈" in name_key:
                    mother_key = name_key
                    break
            if mother_key and mother_key not in matched_names:
                matched_paths.append(assets_dict[mother_key])
                matched_names.append(mother_key)

        # 如果包含妹妹，寻找包含“妹妹”或“玩伴”的键
        if has_sister_specific:
            sister_key = None
            for name_key in assets_dict.keys():
                if any(k in name_key for k in ["妹妹", "玩伴", "女儿", "小孩", "童年"]):
                    sister_key = name_key
                    break
            if sister_key and sister_key not in matched_names:
                matched_paths.append(assets_dict[sister_key])
                matched_names.append(sister_key)

    elif category == "scenes":
        # 场景的动态模糊匹配：如果输入里有代表场景特征的词，资产里也有，就建立绑定
        for name_key, path_val in assets_dict.items():
            if name_key not in matched_names:
                scene_keywords = ["厨房", "画桌", "卧室", "工作室", "房间", "创作空间", "温室", "花园", "松树", "长椅", "草坪", "草地", "站台", "候车亭", "修理铺", "码头", "街", "路"]
                for kw in scene_keywords:
                    if kw in target_string and kw in name_key:
                        matched_paths.append(path_val)
                        matched_names.append(name_key)
                        break
                        
    return matched_paths, matched_names

