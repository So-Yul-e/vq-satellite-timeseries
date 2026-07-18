from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID
from datetime import date
from app.models.satellite import Satellite
from app.schemas.satellite import SatelliteCreate


class SatelliteService:
    def __init__(self, db: Session):
        self.db = db
    
    def create_satellite(
        self,
        user_id: UUID,
        file_path: str,
        thumbnail_path: str,
        metadata: dict,
        capture_date: Optional[str] = None,
        image_type_id: Optional[int] = None
    ) -> Satellite:
        """위성 영상 생성"""
        satellite = Satellite(
            user_id=user_id,
            file_path=file_path,
            thumbnail_path=thumbnail_path,
            image_type_id=image_type_id,
            file_size=metadata.get("file_size"),
            width=metadata.get("width"),
            height=metadata.get("height"),
            channels=metadata.get("channels"),
            capture_date=date.fromisoformat(capture_date) if capture_date else None,
            latitude_min=metadata.get("latitude_min"),
            latitude_max=metadata.get("latitude_max"),
            longitude_min=metadata.get("longitude_min"),
            longitude_max=metadata.get("longitude_max"),
            metadata_json=metadata,
            status="uploaded"
        )
        
        self.db.add(satellite)
        self.db.commit()
        self.db.refresh(satellite)
        
        return satellite
    
    def get_satellite(self, satellite_id: UUID) -> Optional[Satellite]:
        """위성 영상 조회"""
        return self.db.query(Satellite).filter(Satellite.id == satellite_id).first()
    
    def list_satellites(
        self,
        user_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Satellite]:
        """위성 영상 목록 조회"""
        query = self.db.query(Satellite)
        
        if user_id:
            query = query.filter(Satellite.user_id == user_id)
        
        return query.order_by(Satellite.created_at.desc()).offset(skip).limit(limit).all()
