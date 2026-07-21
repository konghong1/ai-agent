import httpx
import time
import json
import threading

token = "$TOKEN"
results = {}

def send_chat(msg_id):
    start = time.time()
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                "http://localhost:8010/api/chat",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"message": f"测试消息 {msg_id}"}
            )
            elapsed = time.time() - start
            results[msg_id] = {"status": resp.status_code, "time": elapsed}
            print(f"请求 {msg_id}: HTTP {resp.status_code}, 耗时 {elapsed:.1f}s")
    except Exception as e:
        results[msg_id] = {"error": str(e), "time": time.time() - start}
        print(f"请求 {msg_id}: 异常 {e}")

# 并发发两个请求
print("=== 并发测试：同时发两个请求 ===")
t1 = threading.Thread(target=send_chat, args=(1,))
t2 = threading.Thread(target=send_chat, args=(2,))
start_all = time.time()
t1.start()
t2.start()
t1.join()
t2.join()
total = time.time() - start_all

print(f"\n总耗时: {total:.1f}s")
print(f"请求1 耗时: {results.get(1, {}).get('time', 0):.1f}s")
print(f"请求2 耗时: {results.get(2, {}).get('time', 0):.1f}s")

# 如果总耗时 << 请求1 + 请求2，说明并发生效
r1 = results.get(1, {}).get('time', 0)
r2 = results.get(2, {}).get('time', 0)
if r1 > 0 and r2 > 0:
    if total < max(r1, r2) * 1.5:
        print("\n✅ 并发测试通过：两个请求并行处理（总耗时 ≈ 单请求耗时）")
    else:
        print("\n❌ 并发测试失败：请求串行处理（总耗时 ≈ 请求1 + 请求2）")
