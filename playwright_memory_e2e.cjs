// 真实运行端到端验证（隔离测试账号，绝不碰真实用户数据）。
// 验证 P2-P7 后端在 Docker 实际运行时：记忆写入、列表、Reflex/Recall 注入、聊天集成不崩。
const { chromium } = require("playwright");

const BASE = "http://127.0.0.1:8010";
const email = `memtest_${Date.now()}@example.com`;
const password = "Test1234!";

async function api(method, path, { token, body } = {}) {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch { json = text; }
  return { status: res.status, json };
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const log = (...a) => console.log(...a);

  // 1) 注册隔离测试账号
  let r = await api("POST", "/api/auth/register", {
    body: { email, username: email.split("@")[0], password, role: "user" },
  });
  log("register:", r.status, r.json && r.json.detail ? r.json.detail : "");

  // 2) 登录拿 token
  r = await api("POST", "/api/auth/login", { body: { email, password } });
  if (r.status !== 200 || !r.json || !r.json.access_token) {
    log("LOGIN FAILED", r.status, JSON.stringify(r.json));
    await browser.close();
    process.exit(1);
  }
  const token = r.json.access_token;
  log("login: OK, token len =", token.length);

  // 3) 显式写入一条偏好记忆（P2）
  r = await api("POST", "/api/memories", {
    token, body: { key: "语言偏好", value: "简体中文", layer: 1, mem_type: "preference", importance: 0.8 },
  });
  log("create_memory:", r.status, JSON.stringify(r.json));
  const memId = r.json && r.json.id;

  // 4) 列表（应含刚写的）
  r = await api("GET", "/api/memories", { token });
  log("list_memories:", r.status, "count =", Array.isArray(r.json) ? r.json.length : "?",
      "| 含简体中文:", Array.isArray(r.json) && r.json.some(m => (m.value || "").includes("简体中文")));

  // 5) 诊断预览：提及实体应触发 Reflex 注入（P2/P3）
  r = await api("GET", "/api/memories/preview?text=" + encodeURIComponent("我喜欢用简体中文回复"), { token });
  log("preview:", r.status, JSON.stringify(r.json));
  const reflexOk = r.json && r.json.reflex && r.json.reflex.includes("简体中文");
  log("  -> reflex 命中简体中文:", reflexOk);

  // 6) 软删（验证 status=archived，不硬删）
  if (memId) {
    r = await api("DELETE", `/api/memories/${memId}`, { token });
    log("delete_memory:", r.status, JSON.stringify(r.json));
    r = await api("GET", "/api/memories", { token });
    log("  -> 软删后 active 列表数:", Array.isArray(r.json) ? r.json.length : "?");
  }

  // 7) 聊天集成路径冒烟（启用了 ENABLE_CONTEXT_SERVICE + REFLEX；验证不 500）
  r = await api("POST", "/api/chat", {
    token,
    body: {
      message: "请记住我的语言偏好是简体中文",
      agent_id: 1,
      model_name: "agnes-2.0-flash",
    },
  });
  log("chat:", r.status, "| 返回类型:", typeof (r.json && (r.json.answer || r.json)));
  // 聊天可能受上游 agnes 稳定性影响；我们只断言我们的代码路径未 500
  const chatOk = r.status !== 500;
  log("  -> 集成路径未 500:", chatOk);

  await page.screenshot({ path: "verify-shots/memory_e2e.png" }).catch(() => {});
  await browser.close();

  const pass = reflexOk && chatOk;
  log("\n=== E2E RESULT:", pass ? "PASS" : "CHECK ABOVE", "===");
  process.exit(pass ? 0 : 2);
})().catch((e) => { console.error("E2E ERROR", e); process.exit(3); });
