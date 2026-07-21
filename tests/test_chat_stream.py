#!/usr/bin/env python
"""Test chat stream and capture SSE events."""
import json
import sys
import urllib.request
import urllib.error

# Get token
login_data = json.dumps({"email": "admin@example.com", "password": "admin123"}).encode()
req = urllib.request.Request(
    "http://localhost:8010/api/auth/login",
    data=login_data,
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    token = json.loads(resp.read())["access_token"]
print(f"Got token: {token[:30]}...")

# Send chat request
chat_data = {
    "message": "你好",
    "thread_id": None,
    "template_id": None,
    "provider_id": 3,
    "provider_type": "openai-compatible",
    "model_name": "agnes-2.0-flash",
    "reference_images": None,
    "agent_id": None,
}
print(f"Sending chat: {chat_data}")

req = urllib.request.Request(
    "http://localhost:8010/api/chat-stream",
    data=json.dumps(chat_data).encode(),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
    },
)

print("\n=== SSE Stream Events ===")
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        for line in resp:
            line = line.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            print(line)
            if "error" in line.lower() and '"error"' in line:
                break
            if '"answer"' in line and '"thread_id"' in line:
                # got final answer
                pass
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code}")
    print(e.read().decode())
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
