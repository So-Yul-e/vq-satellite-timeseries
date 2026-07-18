"""전국 태양광 패널 탐지 결과 API"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import logging

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.solar_panel import SolarPanel
from app.services.panel_permit_matching_service import PanelPermitMatchingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/solar-panels", tags=["Solar Panels"])


# Pydantic schemas
class SolarPanelResponse(BaseModel):
    id: str
    detection_id: str
    latitude: float
    longitude: float
    area_m2: float
    confidence: float
    panel_count: int
    status: str
    is_illegal: bool
    description: Optional[str]
    detection_date: Optional[str]
    thumbnail_url: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class SolarPanelListResponse(BaseModel):
    total: int
    panels: List[SolarPanelResponse]
    bbox: Optional[dict] = None


class BBoxRequest(BaseModel):
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float


@router.get("/all", response_model=SolarPanelListResponse)
async def get_all_panels(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, le=10000),
    status: Optional[str] = Query(None, description="detected, verified, illegal_confirmed, legal_confirmed"),
    is_legal: Optional[bool] = Query(None),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    전국 모든 태양광 패널 조회

    Args:
        skip: 건너뛸 개수
        limit: 최대 반환 개수 (기본 1000, 최대 10000)
        status: 필터링할 상태
        is_legal: 합법 여부 필터
        min_confidence: 최소 신뢰도
    """
    query = db.query(SolarPanel)

    # 필터링
    if status:
        query = query.filter(SolarPanel.status == status)

    if is_legal is not None:
        query = query.filter(SolarPanel.is_legal == is_legal)

    query = query.filter(SolarPanel.detection_confidence >= min_confidence)

    # 총 개수
    total = query.count()

    # 페이징
    panels = query.order_by(SolarPanel.created_at.desc()).offset(skip).limit(limit).all()

    # Bounding box 계산
    bbox = None
    if panels:
        lats = [p.center_latitude for p in panels]
        lons = [p.center_longitude for p in panels]
        bbox = {
            "lat_min": min(lats),
            "lat_max": max(lats),
            "lon_min": min(lons),
            "lon_max": max(lons)
        }

    return {
        "total": total,
        "panels": [p.to_dict() for p in panels],
        "bbox": bbox
    }


@router.post("/in-bbox", response_model=SolarPanelListResponse)
async def get_panels_in_bbox(
    bbox: BBoxRequest,
    status: Optional[str] = Query(None),
    is_legal: Optional[bool] = Query(None),
    min_confidence: float = Query(0.0),
    limit: int = Query(5000, le=10000),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    지정된 영역(Bounding Box) 내의 태양광 패널 조회

    Args:
        bbox: 영역 좌표 (lat_min, lat_max, lon_min, lon_max)
        status: 필터링할 상태
        is_legal: 합법 여부 필터
        min_confidence: 최소 신뢰도
        limit: 최대 반환 개수
    """
    query = db.query(SolarPanel).filter(
        and_(
            SolarPanel.center_latitude >= bbox.lat_min,
            SolarPanel.center_latitude <= bbox.lat_max,
            SolarPanel.center_longitude >= bbox.lon_min,
            SolarPanel.center_longitude <= bbox.lon_max
        )
    )

    # 필터링
    if status:
        query = query.filter(SolarPanel.status == status)

    if is_legal is not None:
        query = query.filter(SolarPanel.is_legal == is_legal)

    query = query.filter(SolarPanel.detection_confidence >= min_confidence)

    # 총 개수
    total = query.count()

    # 제한
    panels = query.order_by(SolarPanel.detection_confidence.desc()).limit(limit).all()

    return {
        "total": total,
        "panels": [p.to_dict() for p in panels],
        "bbox": {
            "lat_min": bbox.lat_min,
            "lat_max": bbox.lat_max,
            "lon_min": bbox.lon_min,
            "lon_max": bbox.lon_max
        }
    }


@router.get("/statistics")
async def get_statistics(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """전국 태양광 패널 통계"""
    total_panels = db.query(func.count(SolarPanel.id)).scalar()
    illegal_panels = db.query(func.count(SolarPanel.id)).filter(SolarPanel.is_legal == False).scalar()

    avg_confidence = db.query(func.avg(SolarPanel.detection_confidence)).scalar()
    total_area = db.query(func.sum(SolarPanel.area_m2)).scalar()

    # 상태별 개수
    status_counts = db.query(
        SolarPanel.status,
        func.count(SolarPanel.id)
    ).group_by(SolarPanel.status).all()

    return {
        "total_panels": total_panels or 0,
        "illegal_panels": illegal_panels or 0,
        "legal_panels": (total_panels or 0) - (illegal_panels or 0),
        "avg_confidence": float(avg_confidence) if avg_confidence else 0.0,
        "total_area_m2": float(total_area) if total_area else 0.0,
        "total_area_km2": (float(total_area) / 1_000_000) if total_area else 0.0,
        "status_breakdown": {status: count for status, count in status_counts}
    }


@router.get("/heatmap")
async def get_heatmap_data(
    grid_size: float = Query(0.1, description="Grid size in degrees"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    히트맵용 그리드 데이터

    Args:
        grid_size: 그리드 크기 (degrees, 기본 0.1 = ~11km)
    """
    # 위도/경도를 grid_size로 나눠서 그리드 생성
    grid_data = db.query(
        func.floor(SolarPanel.center_latitude / grid_size).label('grid_lat'),
        func.floor(SolarPanel.center_longitude / grid_size).label('grid_lon'),
        func.count(SolarPanel.id).label('count'),
        func.sum(SolarPanel.area_m2).label('total_area'),
        func.avg(SolarPanel.detection_confidence).label('avg_confidence')
    ).group_by('grid_lat', 'grid_lon').all()

    return {
        "grid_size": grid_size,
        "cells": [
            {
                "lat": float(row.grid_lat) * grid_size + grid_size / 2,
                "lon": float(row.grid_lon) * grid_size + grid_size / 2,
                "count": row.count,
                "total_area_m2": float(row.total_area) if row.total_area else 0.0,
                "avg_confidence": float(row.avg_confidence) if row.avg_confidence else 0.0
            }
            for row in grid_data
        ]
    }


@router.get("/{panel_id}", response_model=SolarPanelResponse)
async def get_panel_by_id(
    panel_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """특정 패널 상세 조회"""
    panel = db.query(SolarPanel).filter(
        or_(
            SolarPanel.id == panel_id,
            SolarPanel.detection_id == panel_id
        )
    ).first()

    if not panel:
        raise HTTPException(status_code=404, detail="Panel not found")

    return panel.to_dict()


@router.post("/verify-legality")
async def verify_legality(
    background_tasks: BackgroundTasks,
    radius_m: float = Query(150, description="허가 데이터 검색 반경 (미터)"),
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    """
    모든 AI 탐지 패널의 불법 여부를 검증

    각 패널 위치에서 반경 내에 허가 데이터가 있는지 확인하고 is_illegal 필드 업데이트
    """
    # 백그라운드에서 실행
    background_tasks.add_task(verify_all_panels_legality, radius_m)

    return {
        "message": "Legality verification started in background",
        "radius_m": radius_m
    }


def verify_all_panels_legality(radius_m: float = 150):
    """
    모든 패널의 불법 여부를 검증하는 백그라운드 작업

    PostGIS ST_DWithin 기반 매칭(PanelPermitMatchingService)을 배치 단위로 반복 호출한다.
    """
    from app.core.database import SessionLocal

    db = SessionLocal()
    BATCH_SIZE = 1000

    try:
        matching_service = PanelPermitMatchingService(db)
        radius_km = radius_m / 1000.0

        total_panels = db.query(func.count(SolarPanel.id)).scalar() or 0
        logger.info(f"총 {total_panels}개 패널의 불법 여부 검증 시작 (반경: {radius_m}m)")

        legal_count = 0
        illegal_count = 0
        processed = 0
        skip = 0

        while skip < total_panels:
            result = matching_service.batch_match_panels(
                limit=BATCH_SIZE, skip=skip, radius_km=radius_km
            )
            processed += result["total_processed"]
            legal_count += result["legal"]
            illegal_count += result["illegal"]
            skip += BATCH_SIZE

            logger.info(
                f"진행 중... {processed}/{total_panels} (합법: {legal_count}, 불법: {illegal_count})"
            )

            if result["total_processed"] == 0:
                break

        logger.info(f"✅ 불법 여부 검증 완료!")
        logger.info(f"  - 합법 (허가 있음): {legal_count}개")
        logger.info(f"  - 불법 의심 (허가 없음): {illegal_count}개")

    except Exception as e:
        logger.error(f"불법 여부 검증 실패: {e}")
        db.rollback()

    finally:
        db.close()


def check_permit_at_location(
    latitude: float,
    longitude: float,
    radius_m: float,
    db: Session
) -> tuple[bool, Optional[dict], float]:
    """
    특정 위치에 허가가 있는지 확인 (PostGIS ST_DWithin/ST_Distance)

    PanelPermitMatchingService.match_coordinates_with_permits()에 위임한다.

    Returns:
        (has_permit, nearest_permit_info, distance_m)
    """
    match_result = PanelPermitMatchingService(db).match_coordinates_with_permits(
        latitude=latitude, longitude=longitude, radius_m=radius_m
    )
    distance_m = match_result.get("nearest_permit_distance_m")
    return (
        bool(match_result.get("has_permit")),
        match_result if match_result.get("nearest_permit_id") else None,
        float(distance_m) if distance_m is not None else float('inf'),
    )
