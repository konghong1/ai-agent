import sqlite3

conn = sqlite3.connect("D:/workspace/ai-agent/agent.db")
cur = conn.cursor()

# Check existing data
cur.execute("SELECT COUNT(*) FROM providers")
print("Providers count:", cur.fetchone()[0])
cur.execute("SELECT id, name, user_id, is_default FROM providers")
for r in cur.fetchall():
    print("  Provider:", r)

cur.execute("SELECT COUNT(*) FROM provider_models")
print("ProviderModels count:", cur.fetchone()[0])
cur.execute("SELECT * FROM provider_models")
for r in cur.fetchall():
    print("  Model:", r)

conn.close()
