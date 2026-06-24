import pathlib

# Read original
orig = pathlib.Path("C:/workspace/ai-agent/web/src/main.jsx").read_text(encoding="utf-8")

# We need to completely rewrite it with all new features
# Let me build it piece by piece
parts = []

# Part 1: Imports and utilities (keep original structure but add new icons)
parts.append("""import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bot,
  BrainCircuit,
  Cable,
  ChevronDown,
  ChevronRight,
  Database,
  KeyRound,
  Library,
  LogOut,
  MessageSquare,
  Palette,
  Plus,
  RefreshCcw,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  Users,
  Settings,
  Wrench
} from "lucide-react";
import "./styles.css";
import { MessageRenderer } from './components';

const TOKEN_KEY = "agent-platform-token";
const THEME_KEY = "agent-platform-theme";
const THEMES = [
  { id: "dark", label: "暗黑默认", icon: "\\ud83c\\udf11" },
  { id: "ice", label: "冰晶色", icon: "\\u2744\\ufe0f" },
  { id: "planet", label: "悬浮星体", icon: "\\ud83c\\udf10" }
];

function authHeaders(token) {
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

async function api(path, { token, method = "GET", body } = {}) {
  const response = await fetch(path, {
    method, headers: token ? authHeaders(token) : { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined
  });
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) { throw new Error(data?.detail || "请求失败"); }
  return data;
}
""")

pathlib.Path("C:/workspace/ai-agent/web/src/main.jsx").write_text("".join(parts), encoding="utf-8")
print("Part 1 written")