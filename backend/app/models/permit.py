from __future__ import annotations
from sqlalchemy import Column, String, DateTime
import uuid
from app.core.database import Base
from sqlalchemy.dialects.postgresql import UUID


class PermitSyncLog(Base):
    __tablename__ = "permit_sync_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sync_type = Column(String(50), nullable=False, index=True)  # forest_land, energy_subsidy, building_permit, solar_permit_json
    sync_status = Column(String(20), nullable=False, index=True)  # success, failed, running, partial
    records_synced = Column(String)  # INTEGER 대신 String으로 (확장성, NULL 허용)
    records_updated = Column(String)  # 추가 (NULL 허용)
    records_failed = Column(String)  # INTEGER 대신 String으로 (NULL 허용)
    error_message = Column(String)  # NULL 허용
    source_file = Column(String(500))  # JSON 파일 경로 등 (NULL 허용)
    started_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime)  # NULL 허용
