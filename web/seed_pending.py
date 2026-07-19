import sys, time
sys.path.insert(0, '/c/workspace/ai-agent')
from app.core.database import SessionLocal
from app.models import User, PendingMemory

db = SessionLocal()
admin = db.query(User).filter_by(email='admin@example.com').first()
assert admin, 'admin not found'

# 清掉所有遗留 pending（仅 admin），保证环境干净
old = db.query(PendingMemory).filter_by(user_id=admin.id, status='pending').all()
for p in old:
    db.delete(p)
db.commit()
print('cleared stale pending:', len(old))

uid = int(time.time() * 1000)
cand = f"确定性验证键{uid}:用于验证接受按钮的确定性候选"
p = PendingMemory(user_id=admin.id, candidate=cand, status='pending')
db.add(p)
db.commit()
db.refresh(p)
print('SEEDED_PENDING_ID=' + str(p.id))
db.close()
