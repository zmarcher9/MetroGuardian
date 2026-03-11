"""
Test script to verify database connectivity.
This simulates what happens during FastAPI app startup.
"""
import asyncio
import logging
from sqlalchemy import text
from app.core.logging_config import setup_logging
from app.core.config import get_settings
from app.db.session import engine

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)


async def test_database_connectivity():
    """
    Test database connectivity - same function as in main.py
    """
    try:
        settings = get_settings()
        logger.info("Testing database connectivity...")
        
        # Test connection by executing a simple query
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            row = result.fetchone()
            logger.info(f"Query result: {row[0]}")
        
        logger.info("Database connectivity test PASSED")
        logger.info(f"Database URL: {settings.get_database_url_masked()}")
        return True
    except Exception as e:
        logger.error(f"Database connectivity test FAILED: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.debug(f"Full traceback: {traceback.format_exc()}")
        return False
    finally:
        # Clean up
        await engine.dispose()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Database Connectivity Test")
    print("="*60 + "\n")
    
    result = asyncio.run(test_database_connectivity())
    
    print("\n" + "="*60)
    if result:
        print("SUCCESS: Test completed successfully!")
    else:
        print("FAILED: Test failed - check logs above for details")
        print("\nCommon issues:")
        print("  - Database server is not running")
        print("  - Database hostname/port incorrect in .env file")
        print("  - Database credentials incorrect")
        print("  - Network/firewall blocking connection")
    print("="*60 + "\n")

