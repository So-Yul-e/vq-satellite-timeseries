"""
태양광 허가 데이터 API 엔드포인트
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, cast, Float
from typing import List, Optional
from datetime import datetime
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.solar_permit import (
    SolarPermitResponse,
    SolarPermitListResponse,
    SolarPermitStatsResponse,
    SolarPermitNearbyRequest
)
from app.models.solar_permit import SolarPermit
from app.models.permit import PermitSyncLog

router = APIRouter(prefix="/solar-permits", tags=["Solar Permits"])


@router.get("/", response_model=SolarPermitListResponse)
def get_solar_permits(
    skip: int = Query(0, ge=0, description="건너뛸 레코드 수"),
    limit: int = Query(100, ge=1, le=1000, description="조회할 레코드 수"),
    institution_name: Optional[str] = Query(None, description="기관명 필터"),
    operation_status: Optional[str] = Query(None, description="운영상태 필터"),
    min_capacity: Optional[float] = Query(None, description="최소 용량(kW)"),
    max_capacity: Optional[float] = Query(None, description="최대 용량(kW)"),
    installation_year: Optional[str] = Query(None, description="설치 연도"),
    has_coordinates: Optional[bool] = Query(None, description="좌표 데이터 유무"),
    search: Optional[str] = Query(None, description="시설명 검색"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    태양광 허가 데이터 목록 조회

    - 페이지네이션 지원
    - 다양한 필터링 옵션
    """
    # 기본 쿼리
    query = db.query(SolarPermit)

    # 필터링
    if institution_name:
        query = query.filter(SolarPermit.institution_name.ilike(f"%{institution_name}%"))

    if operation_status:
        query = query.filter(SolarPermit.operation_status == operation_status)

    if min_capacity is not None:
        query = query.filter(SolarPermit.capacity >= min_capacity)

    if max_capacity is not None:
        query = query.filter(SolarPermit.capacity <= max_capacity)

    if installation_year:
        query = query.filter(SolarPermit.installation_year == installation_year)

    if has_coordinates is not None:
        if has_coordinates:
            query = query.filter(
                and_(
                    SolarPermit.latitude.isnot(None),
                    SolarPermit.longitude.isnot(None)
                )
            )
        else:
            query = query.filter(
                or_(
                    SolarPermit.latitude.is_(None),
                    SolarPermit.longitude.is_(None)
                )
            )

    if search:
        query = query.filter(
            or_(
                SolarPermit.facility_name.ilike(f"%{search}%"),
                SolarPermit.road_address.ilike(f"%{search}%")
            )
        )

    # 전체 개수
    total = query.count()

    # 페이지네이션 및 정렬
    permits = query.order_by(SolarPermit.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": permits
    }


@router.get("/stats", response_model=SolarPermitStatsResponse)
def get_solar_permits_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    태양광 허가 데이터 통계 조회

    - 전체 건수
    - 좌표 있는 데이터 건수
    - 총 용량
    - 평균 용량
    - 기관별 통계
    """
    # 전체 통계
    total_stats = db.query(
        func.count(SolarPermit.id).label("total"),
        func.count(SolarPermit.latitude).label("with_coordinates"),
        func.sum(SolarPermit.capacity).label("total_capacity"),
        func.avg(SolarPermit.capacity).label("avg_capacity"),
        # 데이터 기준 시각 = 마지막 임포트 시각(수동 임포트 스냅샷임을 UI에 표시)
        func.max(SolarPermit.created_at).label("data_as_of"),
    ).first()

    # 기관별 통계
    institution_stats = db.query(
        SolarPermit.institution_name,
        func.count(SolarPermit.id).label("count"),
        func.sum(SolarPermit.capacity).label("total_capacity")
    ).group_by(
        SolarPermit.institution_name
    ).order_by(
        func.count(SolarPermit.id).desc()
    ).limit(10).all()

    # 운영 상태별 통계
    status_stats = db.query(
        SolarPermit.operation_status,
        func.count(SolarPermit.id).label("count")
    ).filter(
        SolarPermit.operation_status.isnot(None)
    ).group_by(
        SolarPermit.operation_status
    ).all()

    # 연도별 통계
    year_stats = db.query(
        SolarPermit.installation_year,
        func.count(SolarPermit.id).label("count")
    ).filter(
        SolarPermit.installation_year.isnot(None)
    ).group_by(
        SolarPermit.installation_year
    ).order_by(
        SolarPermit.installation_year.desc()
    ).limit(10).all()

    # SL-H1: 주간 자동 동기화(permit_sync_logs) 실행 이력 노출
    # — 프론트가 "마지막 동기화 N일 전 / 실패" 배지를 그릴 재료.
    # 마지막 "성공" 동기화 완료 시각
    last_success_sync = db.query(PermitSyncLog).filter(
        PermitSyncLog.sync_status == "success"
    ).order_by(
        PermitSyncLog.completed_at.desc()
    ).first()

    # 성공 여부와 무관하게 가장 최근 시도된 동기화 상태(진행중/실패도 보여야 함)
    latest_sync = db.query(PermitSyncLog).order_by(
        PermitSyncLog.started_at.desc()
    ).first()

    return {
        "total": total_stats.total or 0,
        # naive UTC → 'Z' 부착(브라우저 로컬 변환용, solar_panel.to_dict와 동일 규약)
        "data_as_of": (total_stats.data_as_of.isoformat() + "Z") if total_stats.data_as_of else None,
        "with_coordinates": total_stats.with_coordinates or 0,
        "total_capacity_kw": float(total_stats.total_capacity or 0),
        "avg_capacity_kw": float(total_stats.avg_capacity or 0),
        "top_institutions": [
            {
                "name": stat.institution_name,
                "count": stat.count,
                "total_capacity": float(stat.total_capacity or 0)
            }
            for stat in institution_stats
        ],
        "by_status": {
            stat.operation_status: stat.count
            for stat in status_stats
        },
        "by_year": {
            stat.installation_year: stat.count
            for stat in year_stats
        },
        # naive UTC → 'Z' 부착, data_as_of와 동일 규약
        "last_sync_at": (
            (last_success_sync.completed_at.isoformat() + "Z")
            if last_success_sync and last_success_sync.completed_at else None
        ),
        "last_sync_status": latest_sync.sync_status if latest_sync else None,
    }


@router.get("/nearby")
def get_nearby_solar_permits(
    latitude: float = Query(..., description="위도"),
    longitude: float = Query(..., description="경도"),
    radius_km: float = Query(10.0, ge=0.1, le=100, description="검색 반경(km)"),
    limit: int = Query(50, ge=1, le=500, description="최대 결과 수"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    특정 위치 근처의 태양광 허가 데이터 검색

    - Haversine 공식을 사용한 거리 계산
    - 좌표가 있는 데이터만 검색
    """
    # 좌표가 있는 데이터만 필터링
    # Haversine 공식으로 거리 계산 (단순화된 버전)
    # 실제로는 PostGIS를 사용하는 것이 더 정확하지만, 현재는 PostGIS가 없으므로 근사값 사용

    # 1도 = 약 111km (위도 기준)
    # 경도는 위도에 따라 달라지지만 한국 평균 약 88km
    lat_diff = radius_km / 111.0
    lng_diff = radius_km / 88.0

    # 사각형 범위로 먼저 필터링 (성능 최적화)
    permits = db.query(SolarPermit).filter(
        and_(
            SolarPermit.latitude.isnot(None),
            SolarPermit.longitude.isnot(None),
            SolarPermit.latitude.between(latitude - lat_diff, latitude + lat_diff),
            SolarPermit.longitude.between(longitude - lng_diff, longitude + lng_diff)
        )
    ).limit(limit).all()

    # 거리 계산 및 정렬
    results = []
    for permit in permits:
        # 단순 유클리드 거리 (근사값)
        lat_km = (float(permit.latitude) - latitude) * 111.0
        lng_km = (float(permit.longitude) - longitude) * 88.0
        distance_km = (lat_km ** 2 + lng_km ** 2) ** 0.5

        if distance_km <= radius_km:
            results.append({
                "permit": SolarPermitResponse.model_validate(permit),
                "distance_km": round(distance_km, 2)
            })

    # 거리순 정렬
    results.sort(key=lambda x: x["distance_km"])

    return {
        "center": {
            "latitude": latitude,
            "longitude": longitude
        },
        "radius_km": radius_km,
        "total": len(results),
        "items": results
    }


@router.get("/{permit_id}", response_model=SolarPermitResponse)
def get_solar_permit(
    permit_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    특정 태양광 허가 데이터 조회
    """
    permit = db.query(SolarPermit).filter(SolarPermit.id == permit_id).first()

    if not permit:
        raise HTTPException(status_code=404, detail="Solar permit not found")

    return permit


@router.get("/search/by-address")
def search_by_address(
    address: str = Query(..., min_length=2, description="주소 검색어"),
    limit: int = Query(50, ge=1, le=500, description="최대 결과 수"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    주소로 태양광 허가 데이터 검색
    """
    permits = db.query(SolarPermit).filter(
        or_(
            SolarPermit.road_address.ilike(f"%{address}%"),
            SolarPermit.lot_address.ilike(f"%{address}%")
        )
    ).limit(limit).all()

    return {
        "query": address,
        "total": len(permits),
        "items": permits
    }
