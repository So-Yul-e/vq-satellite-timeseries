from fastapi import APIRouter, Depends
from app.core.security import get_current_user

router = APIRouter()

@router.get("/")
async def get_users(current_user=Depends(get_current_user)):
    return [{"id": 1, "name": "Test User"}]
