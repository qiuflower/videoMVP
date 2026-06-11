# -*- coding: utf-8 -*-
import os
import requests
import json

api_key = os.environ.get("T8STAR_API_KEY") or "sk-HZ6UTcRmzWCPue0W3S9JL6YN67h0OilXgIHFPxZWunGWfBDr"
url = "https://ai.t8star.org/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}
payload = {
    "model": "gpt-image-2",
    "messages": [
        {
            "role": "user",
            "content": "A cute cat, photorealistic"
        }
    ]
}
res = requests.post(url, json=payload, headers=headers)
print("Status Code:", res.status_code)
try:
    print("Response JSON:", json.dumps(res.json(), ensure_ascii=False, indent=2))
except Exception as e:
    print("Response Text:", res.text)
