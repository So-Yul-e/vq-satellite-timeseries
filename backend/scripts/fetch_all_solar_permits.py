"""
공공데이터포털 API에서 전체 태양광 발전소 허가 데이터를 가져오는 스크립트

사용법:
    python backend/scripts/fetch_all_solar_permits.py
"""

import sys
import json
import os
from pathlib import Path
import logging
from datetime import datetime

# backend 디렉토리를 Python 경로에 추가
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from scripts.fetch_solar_permits_from_api import fetch_all_pages

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """메인 함수"""
    logger.info("="*70)
    logger.info("🌞 전체 태양광 발전소 허가 데이터 가져오기")
    logger.info("="*70)

    # API 설정 확인
    api_key = settings.SOLAR_PERMIT_API_KEY
    api_url = settings.SOLAR_PERMIT_API_URL

    if not api_key or api_key == "test_permit_key":
        logger.error("❌ API 키가 설정되지 않았습니다.")
        sys.exit(1)

    # 출력 디렉토리 생성
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)

    # 출력 파일명
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"solar_permits_all_{timestamp}.json"

    try:
        # 전체 데이터 가져오기
        logger.info("\n📥 API에서 전체 데이터 가져오는 중...")
        logger.info(f"   예상 데이터: ~118,570건")
        logger.info(f"   예상 시간: 15-30분 (요청 제한 방지를 위한 대기 시간 포함)")
        logger.info(f"   ⚠️ 공공데이터포털 요청 제한을 고려하여 호출 간 0.5초 대기")

        all_items = fetch_all_pages(
            api_key=api_key,
            api_url=api_url,
            output_file=str(output_file),
            request_delay=0.5  # API 호출 간 0.5초 대기 (요청 제한 방지)
        )

        logger.info(f"\n✅ 성공!")
        logger.info(f"   총 {len(all_items)}건 가져오기 완료")
        logger.info(f"   저장 위치: {output_file}")

        # 다음 단계 안내
        logger.info(f"\n📌 다음 단계:")
        logger.info(f"   python backend/scripts/import_solar_permits_to_db.py {output_file}")

    except Exception as e:
        logger.error(f"\n❌ 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
