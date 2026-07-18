"""
태양광 패널 탐지-허가 매칭 API 엔드포인트
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.services.panel_permit_matching_service import PanelPermitMatchingService
from app.models.solar_panel import SolarPanel
from app.models.solar_permit import SolarPermit
from app.models.panel_permit_match import PanelPermitMatch

router = APIRouter(prefix="/matching", tags=["Panel-Permit Matching"])


@router.post("/panels/{panel_id}/match")
def match_single_panel(
    panel_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    단일 패널에 대해 허가 데이터 매칭 수행

    - 주변 2km 내 허가 발전소 검색
    - 거리 기반 매칭 수행
    - 불법 여부 판단
    """
    # 패널 조회
    panel = db.query(SolarPanel).filter(SolarPanel.id == panel_id).first()
    if not panel:
        raise HTTPException(status_code=404, detail="Panel not found")

    # 매칭 수행
    matching_service = PanelPermitMatchingService(db)
    result = matching_service.match_panel_with_permits(panel)

    # 매칭 결과 저장
    if result.get("nearest_permit_id"):
        matching_service.save_match_result(
            panel_id=panel.id,
            permit_id=UUID(result["nearest_permit_id"]),
            distance_m=result["nearest_permit_distance_m"],
            match_type=result["match_type"],
            match_confidence=result["match_confidence"],
            area_ratio=result.get("area_ratio")
        )

    # 패널 상태 업데이트
    panel.is_legal = not result["is_illegal"]
    panel.status = "illegal_confirmed" if result["is_illegal"] else "legal_confirmed"
    db.commit()

    return result


@router.post("/batch-match")
def batch_match_panels(
    limit: int = Query(100, ge=1, le=1000, description="처리할 패널 수"),
    skip: int = Query(0, ge=0, description="건너뛸 패널 수"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    """
    여러 패널에 대해 일괄 매칭 수행

    - 대량의 패널을 한 번에 매칭
    - 백그라운드 작업으로 실행 가능
    """
    matching_service = PanelPermitMatchingService(db)
    result = matching_service.batch_match_panels(limit=limit, skip=skip)

    return {
        "status": "completed",
        **result
    }


@router.get("/stats")
def get_matching_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    매칭 통계 조회

    - 전체 패널 수
    - 매칭된 패널 수
    - 불법 패널 수
    - 합법 패널 수
    """
    # 전체 패널 통계
    total_panels = db.query(func.count(SolarPanel.id)).scalar()

    # 매칭 통계
    matching_stats = db.query(
        func.count(func.distinct(PanelPermitMatch.panel_id)).label("matched_panels"),
        func.count(case((PanelPermitMatch.match_type == "exact", 1))).label("exact_matches"),
        func.count(case((PanelPermitMatch.match_type == "nearby", 1))).label("nearby_matches"),
        func.count(case((PanelPermitMatch.match_type == "suspected_illegal", 1))).label("suspected_illegal"),
    ).first()

    # 패널 상태별 통계
    status_stats = db.query(
        SolarPanel.status,
        func.count(SolarPanel.id)
    ).group_by(SolarPanel.status).all()

    # 불법 패널 통계
    illegal_count = db.query(func.count(SolarPanel.id)).filter(
        SolarPanel.is_legal == False
    ).scalar()

    legal_count = db.query(func.count(SolarPanel.id)).filter(
        SolarPanel.is_legal == True
    ).scalar()

    return {
        "total_panels": total_panels,
        "matched_panels": matching_stats.matched_panels if matching_stats else 0,
        "exact_matches": matching_stats.exact_matches if matching_stats else 0,
        "nearby_matches": matching_stats.nearby_matches if matching_stats else 0,
        "suspected_illegal": matching_stats.suspected_illegal if matching_stats else 0,
        "illegal_panels": illegal_count,
        "legal_panels": legal_count,
        "status_breakdown": {
            status: count for status, count in status_stats
        }
    }


@router.get("/panels/{panel_id}/matches")
def get_panel_matches(
    panel_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    특정 패널의 매칭 결과 조회
    """
    # 패널 조회
    panel = db.query(SolarPanel).filter(SolarPanel.id == panel_id).first()
    if not panel:
        raise HTTPException(status_code=404, detail="Panel not found")

    # 매칭 결과 조회
    matches = (
        db.query(PanelPermitMatch, SolarPermit)
        .join(SolarPermit, PanelPermitMatch.permit_id == SolarPermit.id)
        .filter(PanelPermitMatch.panel_id == panel_id)
        .order_by(PanelPermitMatch.distance_m.asc())
        .all()
    )

    return {
        "panel_id": str(panel_id),
        "panel": panel.to_dict(),
        "matches": [
            {
                "match_id": str(match.id),
                "permit_id": str(match.permit_id),
                "facility_name": permit.facility_name,
                "road_address": permit.road_address,
                "capacity_kw": float(permit.capacity) if permit.capacity else None,
                "operation_status": permit.operation_status,
                "distance_m": float(match.distance_m),
                "match_type": match.match_type,
                "match_confidence": float(match.match_confidence) if match.match_confidence else None,
                "area_ratio": float(match.area_ratio) if match.area_ratio else None,
                "status": match.status,
                "matched_at": match.matched_at.isoformat() if match.matched_at else None
            }
            for match, permit in matches
        ]
    }


@router.get("/illegal-panels")
def get_illegal_panels(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    무허가로 의심되는 패널 목록 조회

    - is_legal = False인 패널
    - 우선순위: 신뢰도가 높은 순서
    """
    panels = db.query(SolarPanel).filter(
        SolarPanel.is_legal == False
    ).order_by(
        SolarPanel.detection_confidence.desc()
    ).offset(skip).limit(limit).all()

    total = db.query(func.count(SolarPanel.id)).filter(
        SolarPanel.is_legal == False
    ).scalar()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [panel.to_dict() for panel in panels]
    }
