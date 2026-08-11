"""
Formalizes the old ad-hoc `backend/test_db_connectivity.py` script as a real,
CI-visible test: confirms the configured DATABASE_URL is reachable and that
the ORM schema can actually be created against it.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.db


@pytest.mark.asyncio
async def test_database_is_reachable(db_session: AsyncSession):
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_expected_tables_exist(db_session: AsyncSession):
    result = await db_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    )
    tables = {row[0] for row in result.all()}
    for expected in ("users", "traffic_events", "construction_events", "pipeline_alerts"):
        assert expected in tables
