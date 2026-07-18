from fastapi import APIRouter, Depends

from app.core.security import get_current_user

router = APIRouter()

from datetime import datetime
from typing import List
from pydantic import BaseModel

class Detection(BaseModel):
    id: str
    latitude: float
    longitude: float
    date: str
    status: str  # 'new', 'investigating', 'resolved'
    confidence: float
    description: str
    thumbnail_url: str

@router.get("/", response_model=List[Detection])
async def get_detections(current_user=Depends(get_current_user)):
    # Mock data return
    # Return empty list initially so only real user detections are shown
    return []

