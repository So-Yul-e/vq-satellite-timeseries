"""
태양광 허가 데이터 동기화 Celery 태스크
"""
from __future__ import annotations

import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from uuid import UUID
from celery import Task
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.config import settings
from app.models.permit import PermitSyncLog

# 스크립트 import를 위한 경로 설정
import sys
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

logger = logging.getLogger(__name__)


@celery_app.task(
    name="sync_solar_permits",
    bind=True,
    max_retries=3,
    default_retry_delay=300  # 5분 후 재시도
)
def sync_solar_permits(self: Task):
    """
    공공데이터포털에서 태양광 허가 데이터를 가져와서 DB에 동기화

    주기: 매주 일요일 새벽 3시
    """
    # SL-H1: 동기화 실행 이력을 permit_sync_logs에 남긴다.
    # 이 로그가 없으면 celery stdout뿐이라 컨테이너 재시작 시 소실되고,
    # 동기화가 몇 주째 실패해도 아무도 모르는 침묵 실패가 발생한다.
    # 로그 기록 자체는 best-effort — 실패해도 동기화 본체를 죽이지 않는다.
    sync_log_id = None
    log_db = SessionLocal()
    try:
        sync_log = PermitSyncLog(
            sync_type="solar_permit_json",
            sync_status="running",
            started_at=datetime.utcnow(),
        )
        log_db.add(sync_log)
        log_db.commit()
        sync_log_id = sync_log.id
    except Exception as log_exc:
        logger.warning(f"⚠️ 동기화 시작 이력 기록 실패(무시하고 진행): {log_exc}")
    finally:
        log_db.close()

    try:
        from scripts.fetch_solar_permits_from_api import fetch_all_pages
        from scripts.import_solar_permits_to_db import import_solar_permits_from_json

        logger.info("="*70)
        logger.info("🌞 태양광 허가 데이터 동기화 시작")
        logger.info("="*70)

        # API 설정 확인
        api_key = settings.SOLAR_PERMIT_API_KEY
        api_url = settings.SOLAR_PERMIT_API_URL

        if not api_key or api_key == "test_permit_key":
            logger.error("❌ API 키가 설정되지 않았습니다.")
            _finalize_sync_log(sync_log_id, sync_status="failed", error_message="API key not configured")
            return {
                "status": "failed",
                "error": "API key not configured"
            }

        # 출력 디렉토리 생성
        output_dir = Path("data/sync")
        output_dir.mkdir(parents=True, exist_ok=True)

        # 출력 파일명
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"solar_permits_sync_{timestamp}.json"

        # 시작 시 생성한 running 행에 source_file을 채워 넣는다(출력 파일 경로가
        # 이 시점에야 정해지므로 최초 insert에는 넣지 못했다).
        _update_sync_log_source_file(sync_log_id, str(output_file))

        # 1. API에서 전체 데이터 가져오기
        logger.info("\n📥 API에서 데이터 가져오는 중...")
        all_items = fetch_all_pages(
            api_key=api_key,
            api_url=api_url,
            output_file=str(output_file),
            request_delay=0.5  # 요청 제한 방지
        )

        logger.info(f"✅ API에서 {len(all_items)}건 가져오기 완료")

        # 2. DB에 임포트
        logger.info("\n📝 DB에 임포트 중...")
        db = SessionLocal()
        try:
            # 전량 교체(멱등) — 기존 허가 데이터를 지우고 새 스냅샷으로 원자 교체.
            # 이때 panel_permit_matches가 CASCADE로 함께 지워지므로 아래에서 재매칭한다.
            result = import_solar_permits_from_json(db, str(output_file), replace=True)

            logger.info(f"\n✅ 임포트 완료! 성공: {result['synced']}건 / 실패: {result['failed']}건")

            # 3. 재매칭 — 허가 데이터가 교체돼 기존 매칭(panel_permit_matches)이 전부
            #    삭제됐으므로, 전체 패널을 새 허가 집합에 대해 다시 매칭해 is_legal을
            #    최신화한다. 이 단계가 없으면 무허가/합법 판정이 빈 상태로 남는다.
            logger.info("\n🔗 새 허가 데이터로 전체 패널 재매칭 중...")
            from app.models.solar_panel import SolarPanel
            from app.services.panel_permit_matching_service import PanelPermitMatchingService

            panel_total = db.query(SolarPanel).count()
            match_result = PanelPermitMatchingService(db).batch_match_panels(limit=panel_total, skip=0)
            logger.info(f"✅ 재매칭 완료: {match_result}")

            _finalize_sync_log(
                sync_log_id,
                sync_status="success",
                records_synced=str(result['synced']),
                records_failed=str(result['failed']),
            )

            return {
                "status": "success",
                "synced": result['synced'],
                "failed": result['failed'],
                "total": len(all_items),
                "rematched_panels": panel_total,
                "timestamp": timestamp
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"❌ 동기화 실패: {e}")
        import traceback
        traceback.print_exc()

        _finalize_sync_log(sync_log_id, sync_status="failed", error_message=str(e)[:500])

        # 재시도
        raise self.retry(exc=e)


def _update_sync_log_source_file(sync_log_id: Optional[UUID], source_file: str) -> None:
    """동기화 이력 행에 source_file을 채운다(best-effort, 실패해도 동기화는 계속)."""
    if sync_log_id is None:
        return
    db = SessionLocal()
    try:
        log_row = db.query(PermitSyncLog).filter(PermitSyncLog.id == sync_log_id).first()
        if log_row:
            log_row.source_file = source_file
            db.commit()
    except Exception as exc:
        logger.warning(f"⚠️ 동기화 이력 source_file 갱신 실패(무시하고 진행): {exc}")
    finally:
        db.close()


def _finalize_sync_log(
    sync_log_id: Optional[UUID],
    *,
    sync_status: str,
    records_synced: Optional[str] = None,
    records_failed: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """동기화 이력 행을 성공/실패로 마감한다(best-effort, 실패해도 동기화 본체는 죽이지 않음)."""
    if sync_log_id is None:
        return
    db = SessionLocal()
    try:
        log_row = db.query(PermitSyncLog).filter(PermitSyncLog.id == sync_log_id).first()
        if log_row:
            log_row.sync_status = sync_status
            log_row.completed_at = datetime.utcnow()
            if records_synced is not None:
                log_row.records_synced = records_synced
            if records_failed is not None:
                log_row.records_failed = records_failed
            if error_message is not None:
                log_row.error_message = error_message
            db.commit()
    except Exception as exc:
        logger.warning(f"⚠️ 동기화 이력 마감 기록 실패(무시): {exc}")
    finally:
        db.close()


@celery_app.task(name="test_solar_permit_sync")
def test_solar_permit_sync():
    """동기화 태스크 테스트용"""
    logger.info("🧪 태양광 허가 데이터 동기화 테스트")
    return {
        "status": "test",
        "message": "Celery task is working!"
    }
