from __future__ import annotations
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, date
from uuid import UUID

class SatelliteBase(BaseModel):
    capture_date: Optional[date] = None
    image_type_id: Optional[int] = None

class SatelliteCreate(SatelliteBase):
    pass

class SatelliteResponse(SatelliteBase):
    id: UUID
    user_id: UUID
    file_path: str
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    channels: Optional[int] = None
    latitude_min: Optional[float] = None
    latitude_max: Optional[float] = None
    longitude_min: Optional[float] = None
    longitude_max: Optional[float] = None
    thumbnail_path: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
