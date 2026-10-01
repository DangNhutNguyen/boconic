from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db

router = APIRouter(tags=["Health"])

@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_check():
    """Liveness probe: verifies process is responsive."""
    return {"status": "ok", "service": "boconic-api"}

@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness probe: verifies database connection."""
    try:
        await db.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "connected",
            "service": "boconic-api"
        }
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "database": "disconnected", "error": str(e)}
        )

@router.get("/api/health", status_code=status.HTTP_200_OK)
async def api_health_alias(db: AsyncSession = Depends(get_db)):
    """Backward-compatible health check endpoint."""
    return await readiness_check(db)
