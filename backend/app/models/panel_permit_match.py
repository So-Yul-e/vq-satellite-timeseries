"""태양광 패널 탐지 결과와 허가 데이터 매칭 결과 모델"""
from __future__ import annotations
from sqlalchemy import Column, String, DECIMAL, TIMESTAMP, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
from app.core.database import Base


class PanelPermitMatch(Base):
    """패널-허가 매칭 결과 (database/migrations/020_create_panel_permit_matches.sql)"""
    __tablename__ = "panel_permit_matches"
    __table_args__ = (
        UniqueConstraint("panel_id", "permit_id", name="unique_panel_permit_match"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 관계
    panel_id = Column(UUID(as_uuid=True), ForeignKey("solar_panels.id", ondelete="CASCADE"), nullable=False, index=True)
    permit_id = Column(UUID(as_uuid=True), ForeignKey("solar_permits.id", ondelete="CASCADE"), nullable=False, index=True)

    # 매칭 정보
    distance_m = Column(DECIMAL(10, 2), nullable=False, index=True)
    match_type = Column(String(20), nullable=False, index=True)  # exact, nearby, suspected_illegal
    match_confidence = Column(DECIMAL(5, 4))

    # 비교 정보
    area_ratio = Column(DECIMAL(5, 2))

    # 매칭 상태
    status = Column(String(20), default="pending", index=True)  # pending, confirmed, rejected

    # 메타 정보
    notes = Column(Text)
    # "metadata"는 SQLAlchemy Declarative의 예약어이므로 속성명은 extra_metadata로 매핑
    extra_metadata = Column("metadata", JSONB)

    # 타임스탬프
    matched_at = Column(TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"))
    verified_at = Column(TIMESTAMP)
    verified_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    def __repr__(self):
        return f"<PanelPermitMatch(panel_id={self.panel_id}, permit_id={self.permit_id}, match_type={self.match_type})>"
