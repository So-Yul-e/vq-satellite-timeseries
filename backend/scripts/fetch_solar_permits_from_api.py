"""
공공데이터포털 API에서 실제 태양광 발전소 허가 데이터를 가져오는 스크립트

API: 전국태양광발전소전기사업허가정보표준데이터
URL: https://www.data.go.kr/data/15128507/standard.do

사용법:
    python backend/scripts/fetch_solar_permits_from_api.py
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx  # type: ignore

# backend 디렉토리를 Python 경로에 추가
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_solar_permits_from_api(
    api_key: str,
    api_url: str,
    page: int = 1,
    per_page: int = 1000,
    output_file: str = None,
    retry_count: int = 3,
    retry_delay: int = 5
):
    """
    공공데이터포털 API에서 태양광 발전소 허가 데이터 가져오기

    Args:
        api_key: 공공데이터포털 API 인증키
        api_url: API 엔드포인트 URL
        page: 페이지 번호
        per_page: 페이지당 데이터 수
        output_file: 저장할 JSON 파일 경로
        retry_count: 재시도 횟수
        retry_delay: 재시도 대기 시간 (초)

    Returns:
        데이터 리스트
    """
    last_exception = None
    
    for attempt in range(retry_count):
        try:
            # API 파라미터
            params = {
                "serviceKey": api_key,
                "pageNo": page,
                "numOfRows": per_page,
                "type": "json"  # 응답 형식
            }

            logger.info(f"공공데이터포털 API 호출 중... (페이지: {page}, 시도: {attempt + 1}/{retry_count})")
            logger.info(f"API URL: {api_url}")

            # HTTP 요청
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(api_url, params=params)
                response.raise_for_status()

                # JSON 파싱
                data = response.json()

                # 에러코드 확인 (공공데이터포털 표준 응답)
                if "response" in data:
                    header = data["response"].get("header", {})
                    result_code = header.get("resultCode", "00")
                    result_msg = header.get("resultMsg", "")

                    # 에러코드 확인
                    if result_code != "00":
                        error_msg = f"API 에러 (코드: {result_code}): {result_msg}"
                        
                        # 요청 제한 초과 에러 (22번)
                        if result_code == "22":
                            if attempt < retry_count - 1:
                                wait_time = retry_delay * (attempt + 1) * 2  # 지수 백오프
                                logger.warning(f"⚠️ 요청 제한 초과. {wait_time}초 대기 후 재시도...")
                                time.sleep(wait_time)
                                continue
                            else:
                                logger.error(f"❌ {error_msg}")
                                raise Exception(f"요청 제한 초과: 최대 재시도 횟수 초과")
                        
                        # 기타 에러
                        logger.error(f"❌ {error_msg}")
                        raise Exception(error_msg)

                # 응답 구조 확인 및 데이터 추출
                # 공공데이터포털 표준 응답 형식
                if "response" in data:
                    body = data["response"].get("body", {})
                    items = body.get("items", {})

                    # items가 딕셔너리인 경우
                    if isinstance(items, dict):
                        item_list = items.get("item", [])
                        # item이 단일 객체인 경우 리스트로 변환
                        if isinstance(item_list, dict):
                            item_list = [item_list]
                    # items가 리스트인 경우
                    elif isinstance(items, list):
                        item_list = items
                    else:
                        item_list = []

                    # total_count를 정수로 변환 (문자열일 수 있음)
                    total_count = body.get("totalCount", 0)
                    if isinstance(total_count, str):
                        try:
                            total_count = int(total_count)
                        except ValueError:
                            total_count = 0
                    elif not isinstance(total_count, int):
                        total_count = 0

                    logger.info(f"✅ {len(item_list)}건 조회 완료 (전체: {total_count}건)")

                    # JSON 파일로 저장
                    if output_file and item_list:
                        with open(output_file, 'w', encoding='utf-8') as f:
                            json.dump(item_list, f, ensure_ascii=False, indent=2)
                        logger.info(f"📁 데이터 저장 완료: {output_file}")

                    return {
                        "items": item_list,
                        "total_count": total_count,
                        "page": page,
                        "per_page": per_page
                    }

                # 표준 형식이 아닌 경우 - 리스트 형식
                elif isinstance(data, list):
                    logger.info(f"✅ {len(data)}건 조회 완료")
                    if output_file:
                        with open(output_file, 'w', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        logger.info(f"📁 데이터 저장 완료: {output_file}")

                    return {
                        "items": data,
                        "total_count": len(data),
                        "page": page,
                        "per_page": per_page
                    }

                # 기타 형식
                else:
                    logger.warning(f"예상치 못한 응답 구조: {data}")
                    return {
                        "items": [],
                        "total_count": 0,
                        "page": page,
                        "per_page": per_page,
                        "raw_response": data
                    }

        except httpx.HTTPStatusError as e:
            last_exception = e
            if attempt < retry_count - 1:
                wait_time = retry_delay * (attempt + 1)
                logger.warning(f"⚠️ HTTP 오류: {e.response.status_code}. {wait_time}초 대기 후 재시도...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"HTTP 오류: {e.response.status_code} - {e.response.text}")
                raise
                
        except httpx.RequestError as e:
            last_exception = e
            if attempt < retry_count - 1:
                wait_time = retry_delay * (attempt + 1)
                logger.warning(f"⚠️ 요청 오류: {e}. {wait_time}초 대기 후 재시도...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"요청 오류: {e}")
                raise
                
        except Exception as e:
            last_exception = e
            # API 에러코드 22번은 이미 처리됨
            if "요청 제한 초과" in str(e) or "API 에러" in str(e):
                raise  # 즉시 재시도하지 않고 예외 발생
            elif attempt < retry_count - 1:
                wait_time = retry_delay * (attempt + 1)
                logger.warning(f"⚠️ 오류 발생: {e}. {wait_time}초 대기 후 재시도...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"데이터 가져오기 실패: {e}")
                raise
    
    # 모든 재시도 실패
    if last_exception:
        raise last_exception
    raise Exception("알 수 없는 오류로 데이터를 가져올 수 없습니다.")


def fetch_all_pages(
    api_key: str,
    api_url: str,
    output_file: str = None,
    max_pages: int = None,
    request_delay: float = 0.5
):
    """
    모든 페이지의 데이터를 가져오기

    Args:
        api_key: API 인증키
        api_url: API URL
        output_file: 저장할 파일 경로
        max_pages: 최대 페이지 수 (None이면 전체)
        request_delay: API 호출 간 대기 시간 (초) - 요청 제한 방지

    Returns:
        전체 데이터 리스트
    """
    all_items = []
    page = 1
    per_page = 1000  # 한 페이지당 최대 1000건
    total_count = None  # 전체 개수 (첫 응답에서 확인)

    logger.info(f"⏱️ API 호출 간 대기 시간: {request_delay}초 (요청 제한 방지)")

    while True:
        if max_pages and page > max_pages:
            logger.info(f"최대 페이지 수 도달: {max_pages}")
            break

        # API 호출
        result = fetch_solar_permits_from_api(
            api_key=api_key,
            api_url=api_url,
            page=page,
            per_page=per_page
        )

        items = result["items"]
        if not items:
            logger.info("더 이상 데이터가 없습니다.")
            break

        all_items.extend(items)

        # 전체 개수 확인 (첫 페이지에서 확인)
        if total_count is None:
            total_count = result.get("total_count")
            # total_count를 정수로 변환
            if isinstance(total_count, str):
                try:
                    total_count = int(total_count)
                except (ValueError, TypeError):
                    total_count = None
            elif not isinstance(total_count, int):
                total_count = None
            
            if total_count and total_count > 0:
                estimated_pages = (total_count + per_page - 1) // per_page
                logger.info(f"📊 예상 전체 페이지 수: {estimated_pages}페이지")

        # 진행 상황 출력
        if total_count and isinstance(total_count, int) and total_count > 0:
            progress = (len(all_items) / total_count) * 100
            logger.info(f"📈 진행률: {len(all_items):,}건 / {total_count:,}건 ({progress:.1f}%)")
        else:
            logger.info(f"📈 현재까지 수집: {len(all_items):,}건")

        # 전체 데이터 조회 완료 확인
        if total_count and isinstance(total_count, int) and len(all_items) >= total_count:
            logger.info(f"✅ 전체 데이터 조회 완료: {len(all_items):,}건")
            break

        # 다음 페이지로 이동 전 대기 (요청 제한 방지)
        if request_delay > 0:
            time.sleep(request_delay)

        page += 1

    # 전체 데이터 저장
    if output_file and all_items:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_items, f, ensure_ascii=False, indent=2)
        logger.info(f"📁 전체 데이터 저장 완료: {output_file} ({len(all_items):,}건)")

    return all_items


def main():
    """메인 함수"""
    logger.info("="*70)
    logger.info("🌞 태양광 발전소 허가 데이터 가져오기")
    logger.info("="*70)

    # API 설정 확인
    api_key = settings.SOLAR_PERMIT_API_KEY
    api_url = settings.SOLAR_PERMIT_API_URL

    if not api_key or api_key == "test_permit_key":
        logger.error("❌ API 키가 설정되지 않았습니다.")
        logger.info("\n다음 단계를 진행해주세요:")
        logger.info("1. 공공데이터포털(https://www.data.go.kr) 회원가입")
        logger.info("2. '전국태양광발전소전기사업허가정보표준데이터' 검색 및 활용신청")
        logger.info("3. 발급받은 API 키를 .env 파일에 설정:")
        logger.info("   SOLAR_PERMIT_API_KEY=your_api_key_here")
        logger.info("\n또는 직접 다운로드한 JSON 파일을 사용하려면:")
        logger.info("   python backend/scripts/import_solar_permits.py <json_file_path>")
        sys.exit(1)

    # 출력 디렉토리 생성
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)

    # 출력 파일명
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"solar_permits_{timestamp}.json"

    try:
        # 데이터 가져오기 (첫 페이지만)
        logger.info("\n1️⃣ API에서 데이터 가져오는 중...")
        result = fetch_solar_permits_from_api(
            api_key=api_key,
            api_url=api_url,
            page=1,
            per_page=1000,
            output_file=str(output_file)
        )

        logger.info(f"\n✅ 성공!")
        logger.info(f"   조회된 데이터: {len(result['items'])}건")
        logger.info(f"   전체 데이터: {result['total_count']}건")
        logger.info(f"   저장 위치: {output_file}")

        # 전체 데이터 가져오기 여부 확인
        if result['total_count'] > len(result['items']):
            logger.info(f"\n💡 전체 데이터를 가져오려면 다음 명령어를 실행하세요:")
            logger.info(f"   python backend/scripts/fetch_all_solar_permits.py")

        # 다음 단계 안내
        logger.info(f"\n📌 다음 단계:")
        logger.info(f"   python backend/scripts/import_solar_permits.py {output_file}")

    except Exception as e:
        logger.error(f"\n❌ 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
