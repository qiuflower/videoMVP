# -*- coding: utf-8 -*-
import time
import requests
from core.utils import get_logger

logger = get_logger("llm_client")

def call_t8star_llm(api_key, base_url, model, prompt, max_retries=3, backoff_factor=2, temperature=0.5):
    """
    调用 t8star 文本大模型接口，支持自动重试、退避与 response_format=json 异常降级。
    """
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"}
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=90)
            
            # 兼容性重试：如果不支持 response_format="json_object"，接口可能报错 400，去掉后重试
            if response.status_code == 400:
                payload_fallback = payload.copy()
                if "response_format" in payload_fallback:
                    del payload_fallback["response_format"]
                response = requests.post(url, json=payload_fallback, headers=headers, timeout=90)
                
            if response.status_code in [429, 500, 502, 503, 504]:
                response.raise_for_status()
                
            response.raise_for_status()
            res_json = response.json()
            return res_json["choices"][0]["message"]["content"]
            
        except Exception as e:
            sleep_time = backoff_factor ** attempt
            logger.warning(f"API 文本调用失败 (尝试 {attempt + 1}/{max_retries}): {e}。将在 {sleep_time} 秒后重试...")
            if 'response' in locals() and response is not None:
                try:
                    logger.warning(f"API 返回信息: {response.text[:200]}")
                except:
                    pass
            if attempt < max_retries - 1:
                time.sleep(sleep_time)
            else:
                logger.error(f"API 文本调用在重试 {max_retries} 次后失败。")
                return None

def call_t8star_vision_api(api_key, base_url, model, prompt, base64_images, max_retries=3, backoff_factor=2, temperature=0.2):
    """
    调用 t8star 的 OpenAI 兼容多模态（Vision）接口，传图支持自动重试与兼容回滚。
    """
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # 构造 vision payload
    content_blocks = [{"type": "text", "text": prompt}]
    for img_b64 in base64_images:
        content_blocks.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{img_b64}"
            }
        })
        
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": content_blocks
            }
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"}
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=90)
            
            # 兼容性重试逻辑：如果 response_format 导致 400 错误，自动退回普通模式并重发
            if response.status_code == 400:
                payload_fallback = payload.copy()
                if "response_format" in payload_fallback:
                    del payload_fallback["response_format"]
                response = requests.post(url, json=payload_fallback, headers=headers, timeout=90)
            
            # 如果是限流(429)或服务器错误(5xx)，抛出异常以进入重试循环
            if response.status_code in [429, 500, 502, 503, 504]:
                response.raise_for_status()
                
            response.raise_for_status()
            res_json = response.json()
            return res_json["choices"][0]["message"]["content"]
            
        except Exception as e:
            sleep_time = backoff_factor ** attempt
            logger.warning(f"API 视觉调用失败 (尝试 {attempt + 1}/{max_retries}): {e}。将在 {sleep_time} 秒后重试...")
            if 'response' in locals() and response is not None:
                try:
                    logger.warning(f"API 返回信息: {response.text[:200]}")
                except:
                    pass
            if attempt < max_retries - 1:
                time.sleep(sleep_time)
            else:
                logger.error(f"API 视觉调用在重试 {max_retries} 次后依然失败。")
                return None
