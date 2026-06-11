# -*- coding: utf-8 -*-
import os
import requests
import json
import base64

def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

api_key = os.environ.get("T8STAR_API_KEY") or "sk-HZ6UTcRmzWCPue0W3S9JL6YN67h0OilXgIHFPxZWunGWfBDr"
url = "https://ai.t8star.org/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

# 编码本地林禾参考图
ref_path = "assets/lin_he_ref.png"
if not os.path.exists(ref_path):
    print("Error: assets/lin_he_ref.png does not exist yet.")
    exit(1)

base64_image = encode_image(ref_path)

payload = {
    "model": "gpt-image-2",
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Based on this character reference image, generate a new image of this woman smiling in a library, cinematic lighting, photorealistic --ar 16:9"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    }
                }
            ]
        }
    ]
}

res = requests.post(url, json=payload, headers=headers)
print("Status Code:", res.status_code)
try:
    print("Response JSON:", json.dumps(res.json(), ensure_ascii=False, indent=2))
except Exception as e:
    print("Response Text:", res.text)
