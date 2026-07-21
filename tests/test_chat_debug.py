#!/usr/bin/env python
"""Debug: capture full SSE stream with timing."""
import json
import sys
import time
import urllib.request

# Get token
login_data = json.dumps({"email": "admin@example.com", "password": "admin123"}).encode()
req = urllib.request.Request(
    "http://localhost:8010/api/auth/login",
    data=login_data,
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    token = json.loads(resp.read())["access_token"]

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
start = time.time()
try:
    with urllib.request.urlopen(req, timeout=100) as resp:
        for line in resp:
            elapsed = time.time() - start
            line = line.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            print(f"[{elapsed:.1f}s] {line}")
            if '"error"' in line:
                break
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
