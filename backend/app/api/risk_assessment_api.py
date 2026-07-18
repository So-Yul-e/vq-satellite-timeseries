"""
위험도 평가 API 엔드포인트
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List
import httpx
from app.core.database import get_db
from app.models.risk_assessment import RiskAssessment
from app.models.solar_panel import SolarPanel
from app.services.risk_assessment_service import RiskAssessmentService
from app.core.security import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/panels/{panel_id}/assess", response_model=dict)
async def assess_panel_risk(
    panel_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    태양광 패널 위험도 평가
    
    - 경사도 분석
    - 산 지역 여부 확인 (산 정보 API)
    - 산림 훼손 면적 계산
    - 수계 거리 분석
    - 보호 구역 침범 여부
    """
    service = RiskAssessmentService(db)

    try:
        assessment = await service.assess_panel_risk(panel_id)
        return assessment.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except httpx.TimeoutException as e:
        logger.error(f"위험도 평가 중 외부 API 타임아웃: {e}")
        raise HTTPException(status_code=502, detail="외부 의존 서비스(산 정보/DEM/NDVI 등) 응답 실패: 타임아웃")
    except httpx.HTTPStatusError as e:
        logger.error(f"위험도 평가 중 외부 API 응답 오류: {e}")
        raise HTTPException(status_code=502, detail=f"외부 의존 서비스 응답 실패: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"위험도 평가 중 외부 API 요청 실패: {e}")
        raise HTTPException(status_code=502, detail="외부 의존 서비스(산 정보/DEM/NDVI 등) 요청 실패")
    except Exception as e:
        logger.error(f"위험도 평가 실패(미분류): {e}")
        raise HTTPException(status_code=500, detail="위험도 평가 처리 중 오류가 발생했습니다")


@router.get("/panels/{panel_id}/risk", response_model=dict)
async def get_panel_risk(
    panel_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """패널의 위험도 평가 조회"""
    assessment = db.query(RiskAssessment).filter(
        RiskAssessment.panel_id == panel_id
    ).first()
    
    if not assessment:
        raise HTTPException(status_code=404, detail="위험도 평가를 찾을 수 없습니다")
    
    return assessment.to_dict()


@router.get("/risk-assessments", response_model=List[dict])
async def list_risk_assessments(
    risk_level: str = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """위험도 평가 목록 조회"""
    query = db.query(RiskAssessment)
    
    if risk_level:
        query = query.filter(RiskAssessment.risk_level == risk_level)
    
    assessments = query.order_by(
        RiskAssessment.total_risk_score.desc()
    ).limit(limit).all()
    
    return [assessment.to_dict() for assessment in assessments]
