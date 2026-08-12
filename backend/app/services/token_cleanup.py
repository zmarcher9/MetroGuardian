"""
Refresh-token cleanup: hard-deletes RefreshToken rows well past their
usefulness, so the table doesn't grow unbounded (every login/signup/rotation
inserts a new row and never updates one in place). Rows are kept briefly past
expiry/revocation (refresh_token_cleanup_grace_days) in case they're ever
needed to investigate a reuse/theft event, then purged.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast

from sqlalchemy import delete, or_
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.refresh_token import RefreshToken


async def cleanup_expired_refresh_tokens(db: AsyncSession) -> int:
    """Deletes RefreshToken rows past their grace period. Returns the number deleted."""
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.refresh_token_cleanup_grace_days)
    result = cast(
        CursorResult,
        await db.execute(
            delete(RefreshToken).where(
                or_(
                    RefreshToken.expires_at < cutoff,
                    RefreshToken.revoked_at < cutoff,
                )
            )
        ),
    )
    await db.commit()
    return result.rowcount or 0
