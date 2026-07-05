"""Password reset utility for the AI Agent platform.

Usage:
    python reset_password.py                  # Interactive mode
    python reset_password.py email newpass    # CLI mode

Examples:
    python reset_password.py kh1763751448@gmail.com mynewpass123
    python reset_password.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import User


def reset_password(email: str, new_password: str) -> bool:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email.lower()).first()
        if not user:
            print(f"[ERROR] User not found: {email}")
            return False
        user.password_hash = hash_password(new_password)
        db.commit()
        print(f"[OK] Password reset for: {user.email} (username: {user.username})")
        return True
    except Exception as e:
        print(f"[ERROR] {e}")
        db.rollback()
        return False
    finally:
        db.close()


def list_users() -> None:
    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.id).all()
        print("\nRegistered users:")
        print("-" * 60)
        for u in users:
            print(f"  id={u.id}  email={u.email}  username={u.username}")
        print("-" * 60)
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) == 3:
        reset_password(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 1:
        list_users()
        email = input("\nEnter email to reset: ").strip()
        if not email:
            print("Aborted.")
            sys.exit(1)
        pwd = input("Enter new password (min 6 chars): ").strip()
        if len(pwd) < 6:
            print("Password too short. Aborted.")
            sys.exit(1)
        reset_password(email, pwd)
    else:
        print("Usage: python reset_password.py [email] [new_password]")
        sys.exit(1)
