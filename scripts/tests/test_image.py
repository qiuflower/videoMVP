import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.config import DEFAULT_API_KEY, DEFAULT_BASE_URL

api_key = DEFAULT_API_KEY
url = DEFAULT_BASE_URL.rstrip("/") + "/chat/completions"
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
