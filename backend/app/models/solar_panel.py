"""태양광 패널 탐지 결과 모델"""
from __future__ import annotations
from sqlalchemy import Column, String, Integer, Date, Boolean, ForeignKey, DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
import uuid
from datetime import datetime
from app.core.database import Base


class SolarPanel(Base):
    """태양광 패널 탐지 결과"""
    __tablename__ = "solar_panels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 탐지 정보
    satellite_id = Column(UUID(as_uuid=True), ForeignKey("satellites.id", ondelete="CASCADE"), nullable=False)
    detection_job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=True)

    # 위치 정보 (DB has center_latitude/center_longitude)
    center_latitude = Column(Numeric(10, 7), nullable=False, index=True)
    center_longitude = Column(Numeric(10, 7), nullable=False, index=True)
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)

    # 패널 정보
    panel_polygon = Column(JSONB, nullable=False)  # GeoJSON polygon
    area_m2 = Column(Numeric(12, 2), nullable=False)  # 면적 (m²)
    estimated_capacity_kw = Column(Numeric(10, 2), nullable=True)  # 추정 용량 (kW)
    installation_date_estimated = Column(Date, nullable=True)  # 설치 추정 날짜
    detection_confidence = Column(Numeric(5, 4), nullable=True)  # 탐지 신뢰도 (0-1)

    # 상태
    status = Column(String(20), default='detected', index=True)  # detected, verified, illegal_confirmed, legal_confirmed
    is_legal = Column(Boolean, default=None, index=True, nullable=True)  # 합법 여부
    risk_score = Column(Integer, nullable=True)  # 위험도 점수 (0-100)
    metadata_json = Column(JSONB, nullable=True)  # 부가 메타데이터(위험도 평가, 산 정보 등)

    # 타임스탬프
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    satellite = relationship("Satellite", backref="solar_panels")

    def to_dict(self):
        """딕셔너리로 변환"""
        return {
            "id": str(self.id),
            "detection_id": str(self.id),  # API 호환성
            "satellite_id": str(self.satellite_id) if self.satellite_id else None,
            "detection_job_id": str(self.detection_job_id) if self.detection_job_id else None,
            # API 호환성을 위해 latitude/longitude 제공
            "latitude": float(self.center_latitude) if self.center_latitude else None,
            "longitude": float(self.center_longitude) if self.center_longitude else None,
            "center_latitude": float(self.center_latitude) if self.center_latitude else None,
            "center_longitude": float(self.center_longitude) if self.center_longitude else None,
            "area_m2": float(self.area_m2) if self.area_m2 else None,
            "estimated_capacity_kw": float(self.estimated_capacity_kw) if self.estimated_capacity_kw else None,
            "installation_date_estimated": self.installation_date_estimated.isoformat() if self.installation_date_estimated else None,
            "detection_confidence": float(self.detection_confidence) if self.detection_confidence else None,
            "confidence": float(self.detection_confidence) if self.detection_confidence else None,  # 역호환성
            "panel_count": 1,  # 기본값
            "status": self.status,
            "is_legal": self.is_legal,
            "is_illegal": not self.is_legal if self.is_legal is not None else False,  # 역호환성 (기본 False)
            "description": None,  # 기본값
            # datetime은 UTC(datetime.utcnow) 저장이지만 naive isoformat엔 timezone 표기가
            # 없어 브라우저가 로컬시간으로 오해(KST 기준 9시간 어긋남) — 'Z'를 붙여 UTC 명시.
            # 프론트 toLocaleString()이 알아서 사용자 로컬(KST)로 변환한다.
            "detection_date": (self.created_at.isoformat() + "Z") if self.created_at else None,  # 탐지 시각(생성일)
            "risk_score": self.risk_score,
            "thumbnail_url": None,  # 기본값
            "polygon": self.panel_polygon,  # GeoJSON polygon
            "panel_polygon": self.panel_polygon,
            "created_at": (self.created_at.isoformat() + "Z") if self.created_at else None,
            "updated_at": (self.updated_at.isoformat() + "Z") if self.updated_at else None,
        }
