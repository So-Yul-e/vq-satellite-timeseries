"""
태양광 허가 데이터 스키마
"""
from pydantic import BaseModel, Field, field_serializer
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from uuid import UUID


class SolarPermitBase(BaseModel):
    """태양광 허가 데이터 기본 스키마"""
    facility_name: str = Field(..., description="태양광 발전소명")
    road_address: Optional[str] = Field(None, description="도로명 주소")
    lot_address: Optional[str] = Field(None, description="지번 주소")
    latitude: Optional[Decimal] = Field(None, description="위도")
    longitude: Optional[Decimal] = Field(None, description="경도")
    operation_status: Optional[str] = Field(None, description="운영 상태")
    capacity: Optional[Decimal] = Field(None, description="설비 용량(kW)")
    installation_year: Optional[str] = Field(None, description="설치 연도")
    institution_name: Optional[str] = Field(None, description="관할 기관명")


class SolarPermitResponse(SolarPermitBase):
    """태양광 허가 데이터 응답 스키마"""
    id: UUID
    installation_detail_position: Optional[str] = None
    supply_voltage: Optional[str] = None
    frequency: Optional[str] = None
    installation_area: Optional[str] = None
    detail_usage: Optional[str] = None
    permission_date: Optional[str] = None
    permission_institution: Optional[str] = None
    institution_code: Optional[str] = None
    criteria_date: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_synced_at: datetime

    @field_serializer('id')
    def serialize_id(self, value: UUID, _info) -> str:
        return str(value)

    @field_serializer('latitude', 'longitude', 'capacity')
    def serialize_decimal(self, value: Optional[Decimal], _info) -> Optional[float]:
        return float(value) if value is not None else None

    class Config:
        from_attributes = True


class SolarPermitListResponse(BaseModel):
    """태양광 허가 데이터 목록 응답 스키마"""
    total: int = Field(..., description="전체 개수")
    skip: int = Field(..., description="건너뛴 개수")
    limit: int = Field(..., description="조회 개수")
    items: List[SolarPermitResponse]


class SolarPermitStatsResponse(BaseModel):
    """태양광 허가 데이터 통계 응답 스키마"""
    total: int = Field(..., description="전체 발전소 수")
    with_coordinates: int = Field(..., description="좌표 정보가 있는 발전소 수")
    total_capacity_kw: float = Field(..., description="총 설비 용량(kW)")
    avg_capacity_kw: float = Field(..., description="평균 설비 용량(kW)")
    top_institutions: List[Dict[str, Any]] = Field(..., description="상위 기관 통계")
    by_status: Dict[str, int] = Field(..., description="운영 상태별 통계")
    by_year: Dict[str, int] = Field(..., description="연도별 설치 통계")
    # 데이터가 언제 기준의 스냅샷인지 — 수동 임포트라 자동 갱신되지 않음을 UI에 정직하게 표시
    data_as_of: Optional[str] = Field(None, description="데이터 기준 시각(마지막 임포트, ISO8601 UTC)")
    # SL-H1: 주간 자동 동기화(permit_sync_logs) 실행 이력 — "마지막 동기화 N일 전 / 실패" 배지용
    last_sync_at: Optional[str] = Field(None, description="마지막 성공 동기화 완료 시각(ISO8601 UTC)")
    last_sync_status: Optional[str] = Field(None, description="가장 최근 동기화 상태(success/failed/running/partial)")


class SolarPermitNearbyRequest(BaseModel):
    """근처 태양광 허가 데이터 검색 요청 스키마"""
    latitude: float = Field(..., description="검색 중심 위도")
    longitude: float = Field(..., description="검색 중심 경도")
    radius_km: float = Field(10.0, ge=0.1, le=100, description="검색 반경(km)")
    limit: int = Field(50, ge=1, le=500, description="최대 결과 수")


class SolarPermitNearbyResponse(BaseModel):
    """근처 태양광 허가 데이터 검색 응답 스키마"""
    permit: SolarPermitResponse
    distance_km: float = Field(..., description="거리(km)")
