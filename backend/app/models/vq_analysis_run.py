"""VQ 위치 기반 시계열 변화탐지 실행 이력.

결과가 새로고침 때마다 휘발되던 문제 해소 + "최근 분석" 목록으로 즉시 재표시.
이미지(t1/t2/overlay.png)는 uploads/results/{job_id}/에 이미 영속되므로, 여기엔
재표시에 필요한 결과 JSON(change_result·location·visualization·patch_grid)과
목록 표시용 요약 컬럼만 저장한다.
"""
from __future__ import annotations
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
from app.core.database import Base


class VqAnalysisRun(Base):
    __tablename__ = "vq_analysis_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    buffer_km = Column(Float, nullable=False)
    past_date = Column(String(20))
    t2_date = Column(String(20))  # 실제 T2 시점(계절정합 시 같은-계절 날짜). current_date는 PG 예약어라 회피
    season_aligned = Column(Boolean, default=False)
    # 목록 요약(정렬·미리보기용) — 상세는 result_json에서
    n_total = Column(Integer)
    n_changed = Column(Integer)
    change_percentage = Column(Float)
    solar_panel_count = Column(Integer)
    n_solar_patches = Column(Integer)
    job_id = Column(String(64))  # uploads/results/{job_id} — 이미지 URL 재구성용
    result_json = Column(JSONB)  # 재표시용 전체 결과(task result와 동일 shape)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
