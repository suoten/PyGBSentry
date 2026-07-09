"""Reset admin password to admin123 for testing purposes."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import asyncio
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.core import security
from sqlalchemy import select


async def reset_admin_password():
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.username == "admin")
        result = await session.execute(stmt)
        user = result.scalars().first()
        if not user:
            print("Admin user does not exist!")
            return
        print(f"Found admin user: id={user.id}, is_superuser={user.is_superuser}, is_active={user.is_active}")
        print(f"  role={user.role}, tenant_id={user.tenant_id}")
        print(f"  failed_login_attempts={user.failed_login_attempts}")
        print(f"  locked_until={user.locked_until}")
        # Reset password
        user.hashed_password = security.get_password_hash("admin123")
        user.failed_login_attempts = 0
        user.locked_until = None
        user.is_active = True
        user.is_superuser = True
        user.role = "owner"
        user.tenant_id = user.tenant_id or "default"
        await session.commit()
        print("Admin password has been reset to 'admin123'")
        print("Account lock has been cleared.")


if __name__ == "__main__":
    asyncio.run(reset_admin_password())
