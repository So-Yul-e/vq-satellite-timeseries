"""
태양광 허가 데이터 모델
"""
from sqlalchemy import Column, String, DECIMAL, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geometry
from app.core.database import Base
import uuid


class SolarPermit(Base):
    """태양광 발전소 허가 정보 모델"""
    __tablename__ = "solar_permits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 발전소 정보
    facility_name = Column(String(200), nullable=False, index=True)

    # 위치 정보
    road_address = Column(String(500), index=True)
    lot_address = Column(String(500))
    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)

    # 설치 상세 위치 정보
    installation_detail_position = Column(String(100))

    # 운영 정보
    operation_status = Column(String(50), index=True)

    # 전기 사양
    capacity = Column(DECIMAL(10, 2), index=True)  # 용량 (kW)
    supply_voltage = Column(String(20))  # 전압 (V)
    frequency = Column(String(20))  # 주파수 (Hz)

    # 설치 정보
    installation_year = Column(String(4), index=True)
    installation_area = Column(String(50))

    # 상세 용도
    detail_usage = Column(String(200))

    # 허가 정보
    permission_date = Column(String(20))
    permission_institution = Column(String(200))

    # 기관 정보
    institution_code = Column(String(20), index=True)
    institution_name = Column(String(200), index=True)

    # 메타 정보
    criteria_date = Column(String(20))

    # 원본 데이터
    raw_data = Column(JSONB)

    # 타임스탬프
    created_at = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    updated_at = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    last_synced_at = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))

    def __repr__(self):
        return f"<SolarPermit(id={self.id}, name={self.facility_name})>"
