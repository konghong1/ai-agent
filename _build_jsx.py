import pathlib

P = 'C:/workspace/ai-agent/web/src/main.jsx'
L = []
def a(s=''): L.append(s)

# ============ IMPORTS ============
a('import React, { useEffect, useMemo, useState } from \"react\";')
a('import { createRoot } from \"react-dom/client\";')
a('import {')
a('  Bot, BrainCircuit, Cable, ChevronDown, ChevronRight, Database,')
a('  KeyRound, Library, LogOut, MessageSquare, Palette, Plus, RefreshCcw,')
a('  Send, ShieldCheck, Sparkles, Trash2, Upload, Users, Settings, Wrench')
a('} from \"lucide-react\";')
a('import \"./styles.css\";')
a(\"import { MessageRenderer } from './components';\")
a()
a('const TOKEN_KEY = \"agent-platform-token\";')
a('const THEME_KEY = \"agent-platform-theme\";')
a('const THEMES = [')
a('  { id: \"dark\", label: \"暗黑默认\", icon: \"\\ud83c\\udf11\" },')
a('  { id: \"ice\", label: \"冰晶色\", icon: \"\\u2744\\ufe0f\" },')
a('  { id: \"planet\", label: \"悬浮星体\", icon: \"\\ud83c\\udf10\" }')
a('];')
a()
a('function authHeaders(token) {')
a('  return { \"Content-Type\": \"application/json\", Authorization: Bearer  };')
a('}')
a()
a('async function api(path, { token, method = \"GET\", body } = {}) {')
a('  const response = await fetch(path, {')
a('    method, headers: token ? authHeaders(token) : { \"Content-Type\": \"application/json\" },')
a('    body: body ? JSON.stringify(body) : undefined')
a('  });')
a('  const data = response.status === 204 ? null : await response.json();')
a('  if (!response.ok) { throw new Error(data?.detail || \"Request failed\"); }')
a('  return data;')
a('}')

with open(P, 'w', encoding='utf-8') as f:
    f.write('\n'.join(L))
print(f'Written {len(L)} lines to main.jsx')