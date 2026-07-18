from fastapi import APIRouter, Depends
from app.core.security import require_role

router = APIRouter()

@router.get("/")
async def admin_dashboard(current_user=Depends(require_role("admin"))):
    return {"status": "ok"}
