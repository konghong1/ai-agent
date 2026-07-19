// 验证 Reflex 指针注入在记忆面板「诊断预览」中真实呈现（开关 ENABLE_RETRIEVAL_REFLEX=true 已生效）。
const { chromium } = require("playwright");

const API = "http://127.0.0.1:8010";
const UI = "http://127.0.0.1:5173";
const SHOT = "/c/workspace/ai-agent/verify-shots/memory_reflex_ui_e2e.png";
const email = `rfxui_${Date.now()}@example.com`;
const password = "Test1234!";

async function api(method, path, { token, body } = {}) {
  const res = await fetch(API + path, {
    method,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
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
  const results = {};

  let r = await api("POST", "/api/auth/register", { body: { email, username: email.split("@")[0], password, role: "user" } });
  log("register:", r.status);
  r = await api("POST", "/api/auth/login", { body: { email, password } });
  if (r.status !== 200 || !r.json || !r.json.access_token) { log("LOGIN FAILED", JSON.stringify(r.json)); process.exit(1); }
  const token = r.json.access_token;
  const user = r.json.user || { id: 0, email, username: email.split("@")[0], role: "user" };

  await page.addInitScript((val) => { localStorage.setItem("agent-auth", val); },
    JSON.stringify({ state: { token, user, isAuthenticated: true }, version: 0 }));

  // 写入一条偏好记忆（经 API，确保中文正确）
  r = await api("POST", "/api/memories", { token, body: { key: "语言偏好", value: "简体中文", layer: 1, mem_type: "preference", importance: 0.8 } });
  log("create_memory:", r.status, r.json && r.json.id);

  await page.goto(UI + "/memory", { waitUntil: "networkidle" });
  await page.waitForSelector("text=长期记忆", { timeout: 15000 });

  // 诊断预览：提及该记忆的实体
  await page.getByPlaceholder("例如：我更喜欢用简体中文交流").fill("我喜欢用简体中文回复");
  await page.getByTestId("mem-preview").click();
  await page.waitForSelector(".ant-card", { timeout: 10000 });

  const previewCard = page.locator(".ant-card").first();
  const reflexTag = previewCard.locator(".ant-tag", { hasText: "reflex" });
  const hasReflexTag = await reflexTag.count();
  const cnInPreview = await previewCard.getByText("简体中文", { exact: false }).count();
  results.reflex = hasReflexTag > 0 && cnInPreview > 0;
  log("[ok] 预览卡片出现 reflex 块且含『简体中文』?", results.reflex, "| reflexTag:", hasReflexTag, "| cnInPreview:", cnInPreview);

  await page.screenshot({ path: SHOT, fullPage: true }).catch(() => {});
  await browser.close();
  const pass = results.reflex;
  log("\n=== REFLEX UI E2E RESULT:", pass ? "PASS" : "FAIL", "===", JSON.stringify(results));
  process.exit(pass ? 0 : 2);
})().catch((e) => { console.error("E2E ERROR", e); process.exit(3); });
