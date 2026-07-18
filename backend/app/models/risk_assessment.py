"""위험도 평가 모델"""
from __future__ import annotations
from sqlalchemy import Column, String, Integer, Boolean, DateTime, DECIMAL, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from app.core.database import Base


class RiskAssessment(Base):
    """위험도 평가"""
    __tablename__ = "risk_assessments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    panel_id = Column(UUID(as_uuid=True), ForeignKey("solar_panels.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # 경사도 분석
    slope_degree = Column(DECIMAL(5, 2))  # 경사도 (도)
    slope_risk_score = Column(Integer)  # 경사도 위험 점수 (0-100)
    
    # 산림 훼손 분석
    forest_damage_area_m2 = Column(DECIMAL(12, 2))  # 산림 훼손 면적 (m²)
    forest_risk_score = Column(Integer)  # 산림 훼손 위험 점수 (0-100)
    
    # 수계 거리 분석
    water_distance_m = Column(DECIMAL(10, 2))  # 수계 거리 (m)
    water_risk_score = Column(Integer)  # 수질 위험 점수 (0-100)
    
    # 보호 구역 침범
    protected_area_violation = Column(Boolean, default=False)  # 보호 구역 침범 여부
    protected_risk_score = Column(Integer)  # 보호 구역 위험 점수 (0-100)
    
    # 종합 평가
    total_risk_score = Column(Integer, index=True)  # 종합 위험 점수 (0-100)
    risk_level = Column(String(20), index=True)  # 위험 등급 (low, medium, high, critical)
    
    # 타임스탬프
    assessment_date = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    panel = __import__("app.models.solar_panel", fromlist=["SolarPanel"]).SolarPanel
    
    def to_dict(self):
        """딕셔너리로 변환"""
        return {
            "id": str(self.id),
            "panel_id": str(self.panel_id),
            "slope_degree": float(self.slope_degree) if self.slope_degree else None,
            "slope_risk_score": self.slope_risk_score,
            "forest_damage_area_m2": float(self.forest_damage_area_m2) if self.forest_damage_area_m2 else None,
            "forest_risk_score": self.forest_risk_score,
            "water_distance_m": float(self.water_distance_m) if self.water_distance_m else None,
            "water_risk_score": self.water_risk_score,
            "protected_area_violation": self.protected_area_violation,
            "protected_risk_score": self.protected_risk_score,
            "total_risk_score": self.total_risk_score,
            "risk_level": self.risk_level,
            "assessment_date": self.assessment_date.isoformat() if self.assessment_date else None,
        }
