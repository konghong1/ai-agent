---
name: frontend-debug
description: Troubleshoot and fix frontend/backend issues in the ai-agent project. Covers: page not loading, login/register failures, tsconfig path resolution, .env configuration mismatches, backend startup failures, database path errors, and JSON parsing errors on error responses.
---

# Frontend Debugging Skill

## Quick Diagnostic Checklist

When the user reports "page won't open" or "can't login/register":

### 1. Check Both Services Are Running

```powershell
# Frontend dev server (port 5173)
netstat -ano | findstr "5173"

# Backend API server (port 8000)
netstat -ano | findstr "8000"
```

If either is down, start them:
- Frontend: `cd web && npm run dev`
- Backend: `.venv\Scripts\python.exe -m uvicorn app.server:app --host 0.0.0.0 --port 8000`

### 2. Verify .env Configuration

**CRITICAL**: The backend loads `.env` from the **project root**, NOT from `web/.env`.

Common mistakes:
- API key only in `web/.env` → backend has no OpenAI config
- `DATABASE_URL` points to wrong drive/path → SQLite fails to open

Check:
```powershell
# Ensure root .env exists with correct values
Get-Content .env | Select-String "OPENAI_API_KEY|DATABASE_URL|OPENAI_BASE_URL"
```

Fix database URL if wrong:
```python
# In .env, match actual project path
DATABASE_URL=sqlite:///C:/workspace/ai-agent/agent.db
```

### 3. Check tsconfig.json Path Aliases

If `npm run build` fails with `TS2307: Cannot find module '@/...'`:

The `tsconfig.json` must have `baseUrl` and `paths` matching `vite.config.ts` resolve alias:

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

Without this, `tsc` (which runs before `vite build`) fails even though Vite dev server works fine.

### 4. Check JSON Response Parsing

Error: `Failed to execute 'json' on 'Response': Unexpected end of JSON input`

**Cause**: Frontend calls `res.json()` on error responses that have empty bodies.

**Fix**: Use a safe wrapper that reads text first:
```typescript
async function jsonSafe(res: Response): Promise<any> {
  const text = await res.text()
  return text ? JSON.parse(text) : null
}
```

Apply in both `web/src/services/request.ts` and `web/src/stores/auth.ts`.

### 5. Backend Startup Errors

Common errors and fixes:

| Error | Cause | Fix |
|-------|-------|-----|
| `No module named 'langchain'` | Using system Python, not venv | Use `.venv\Scripts\python.exe` |
| `unable to open database file` | DATABASE_URL has wrong path | Fix `.env` DATABASE_URL |
| `Missing credentials` | No OPENAI_API_KEY in env | Add to root `.env` |

### 6. Verify Endpoints

Test with PowerShell:
```powershell
# Health check
Invoke-WebRequest http://127.0.0.1:8000/health

# Login API
$body = @{email="a@b.com";password="c"} | ConvertTo-Json
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/auth/login" -Method POST -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -ContentType "application/json" -UseBasicParsing
```

### 7. File Integrity

If files seem corrupted (Chinese characters garbled):
```powershell
# Check if file was written with wrong encoding
Get-Content web/index.html -Encoding UTF8
# Compare with git
git show HEAD:web/index.html
```

If git has correct content but file is wrong, restore:
```powershell
git checkout HEAD -- web/index.html
```