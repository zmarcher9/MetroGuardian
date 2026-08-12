"""
Promote a user to admin, directly via the DB.

There is deliberately no HTTP endpoint that can do this - self-service admin
promotion (even admin-promoting-another-user, for the very first admin) would
mean either a public privilege-escalation path or a bootstrapping paradox.
Run this locally against whichever DATABASE_URL is configured in backend/.env.

Usage:
    cd backend
    venv/Scripts/python.exe scripts/promote_admin.py user@example.com
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402


async def promote(email: str) -> None:
    email = email.strip().lower()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            print(f"No user found with email {email!r}. They need to sign up first.")
            return
        if user.is_admin:
            print(f"{email} is already an admin.")
            return
        user.is_admin = True
        await db.commit()
        print(f"{email} is now an admin.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/promote_admin.py <email>")
        raise SystemExit(1)
    asyncio.run(promote(sys.argv[1]))
