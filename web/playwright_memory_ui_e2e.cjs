// 前端记忆面板 UI 端到端验证（隔离测试账号，绝不碰真实用户数据）。
// 驱动真实浏览器：打开 /memory -> 新建记忆 -> 诊断预览 -> 软删除，验证面板行为真实发生。
const { chromium } = require("playwright");

const API = "http://127.0.0.1:8010";
const UI = "http://127.0.0.1:5173";
const SHOT = "/c/workspace/ai-agent/verify-shots/memory_ui_e2e.png";
const email = `memui_${Date.now()}@example.com`;
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

  // 1) 注册 + 登录，拿 token
  let r = await api("POST", "/api/auth/register", { body: { email, username: email.split("@")[0], password, role: "user" } });
  log("register:", r.status, r.json && r.json.detail ? r.json.detail : "ok");
  r = await api("POST", "/api/auth/login", { body: { email, password } });
  if (r.status !== 200 || !r.json || !r.json.access_token) {
    log("LOGIN FAILED", r.status, JSON.stringify(r.json));
    await browser.close();
    process.exit(1);
  }
  const token = r.json.access_token;
  const user = r.json.user || { id: 0, email, username: email.split("@")[0], role: "user" };
  log("login OK, token len", token.length);

  // 在应用 JS 运行前注入 auth（绕过 UI 登录）
  await page.addInitScript((val) => {
    localStorage.setItem("agent-auth", val);
  }, JSON.stringify({ state: { token, user, isAuthenticated: true }, version: 0 }));

  // 2) 打开记忆面板
  await page.goto(UI + "/memory", { waitUntil: "networkidle" });
  await page.waitForSelector("text=长期记忆", { timeout: 15000 });
  results.navAndTitle = true;
  log("[ok] 页面加载，标题「长期记忆」可见；侧边栏「长期记忆」导航存在:",
    (await page.getByText("长期记忆", { exact: false }).count()) > 0);

  // 3) 通过 UI 新建一条记忆
  const key = "语言偏好_" + Date.now();
  const val = "简体中文_" + Date.now();
  await page.getByTestId("mem-new").click();
  try {
    await page.waitForSelector(".ant-modal", { timeout: 8000 });
    log("[debug] 新建弹窗已打开 (.ant-modal 存在)");
  } catch (e) {
    log("[debug] 弹窗未打开！截图诊断");
    await page.screenshot({ path: "/c/workspace/ai-agent/verify-shots/memory_ui_debug.png", fullPage: true }).catch(() => {});
  }
  await page.getByPlaceholder("如：语言偏好").fill(key);
  await page.getByPlaceholder("如：用户偏好使用简体中文").fill(val);
  await page.getByTestId("mem-save").click();
  await page.waitForSelector(`text=${key}`, { timeout: 10000 });
  results.create = true;
  log("[ok] 新建记忆：表格出现新行 ->", key);

  // 4) 诊断预览
  await page.getByPlaceholder("例如：我更喜欢用简体中文交流").fill("我更喜欢用简体中文交流");
  await page.getByTestId("mem-preview").click();
  await page.waitForSelector("text=估算 tokens", { timeout: 10000 });
  results.preview = true;
  log("[ok] 诊断预览：出现「估算 tokens」块");

  // 5) 通过 UI 软删除（点击行内删除 -> 确认弹窗 -> 删除）
  const row = page.locator("tr", { hasText: key });
  await row.getByTestId("mem-del-row").click();
  await page.waitForSelector(".ant-modal-confirm", { timeout: 5000 });
  await page.locator(".ant-modal-confirm .ant-btn-dangerous").click();
  await page.waitForSelector(`text=${key}`, { state: "detached", timeout: 10000 }).catch(() => {});
  const stillThere = await page.locator(`text=${key}`).count();
  results.delete = stillThere === 0;
  log("[ok] 软删除：记忆从 active 列表消失?", stillThere === 0);

  await page.screenshot({ path: SHOT, fullPage: true }).catch(() => {});
  await browser.close();

  const pass = results.navAndTitle && results.create && results.preview && results.delete;
  log("\n=== UI E2E RESULT:", pass ? "PASS" : "FAIL", "===", JSON.stringify(results));
  process.exit(pass ? 0 : 2);
})().catch((e) => { console.error("E2E ERROR", e); process.exit(3); });
