import logging
from fastapi import APIRouter, HTTPException
from app.core.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", tags=["health"])
async def health_check():
    """
    Health check endpoint.
    
    Verifies that:
    - FastAPI app loads correctly
    - Router mounting works
    - Logging works
    - Config loads successfully
    - API responds
    
    Returns:
        dict: Health status and service information
    """
    try:
        # Verify config loads
        settings = get_settings()
        
        logger.info("Health check requested")
        
        return {
            "status": "ok",
            "service": "metroguardian-backend",
            "version": "0.1.0",
            "environment": settings.app_env,
            "config_loaded": True,
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "service": "metroguardian-backend",
                "error": str(e),
                "config_loaded": False,
            }
        )

