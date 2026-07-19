import json, time, urllib.request, urllib.error, sys

API = "http://127.0.0.1:8010"
EMAIL = f"extract_{int(time.time())}@example.com"
PASSWORD = "Test1234!"

def call(method, path, token=None, body=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        return e.code, (raw[:300] if raw else None)

# 1) register
s, j = call("POST", "/api/auth/register", body={
    "email": EMAIL, "username": EMAIL.split("@")[0], "password": PASSWORD, "role": "user"})
print("register:", s, (j if isinstance(j, dict) else j))

# 2) login
s, j = call("POST", "/api/auth/login", body={"email": EMAIL, "password": PASSWORD})
if s != 200 or not isinstance(j, dict) or not j.get("access_token"):
    print("LOGIN FAILED", s, j); sys.exit(1)
token = j["access_token"]
uid = j.get("user", {}).get("id")
print("login ok, uid=", uid)

# 3) chat with a clear preference (no agent_id, no provider_id -> agnes default model)
msg = "以后回复我都以 你好，小花生开头。另外我平时用简体中文。"
s, j = call("POST", "/api/chat", token=token, body={"message": msg})
print("chat status:", s)
if isinstance(j, dict):
    ans = j.get("answer", "")
    print("chat answer head:", ans[:80].replace("\n", " "))
else:
    print("chat body:", j)

# 4) wait for background extraction thread
print("waiting 20s for background extraction thread...")
time.sleep(20)

# 5) check pending candidates
s, j = call("GET", "/api/memories/pending", token=token)
print("pending status:", s)
if isinstance(j, list):
    print("pending count:", len(j))
    for p in j:
        print("  -", p.get("candidate"))
    if j:
        print("RESULT: EXTRACTION WORKS ✅")
    else:
        print("RESULT: no candidate (extraction did not fire)")
else:
    print("pending body:", j)
