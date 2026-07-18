"""
공공데이터포털 태양광 발전소 허가 데이터를 solar_permits 테이블에 import하는 스크립트

사용법:
    python backend/scripts/import_solar_permits_to_db.py <json_file_path>

예시:
    python backend/scripts/import_solar_permits_to_db.py data/solar_permits_20260103_142443.json
"""

import sys
import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import logging

# backend 디렉토리를 Python 경로에 추가
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_json_file(file_path: str) -> List[Dict]:
    """JSON 파일을 파싱하여 허가 데이터 리스트 반환"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, list):
            return data
        else:
            logger.warning(f"예상치 못한 JSON 구조: {type(data)}")
            return []

    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 오류: {e}")
        raise
    except Exception as e:
        logger.error(f"파일 읽기 오류: {e}")
        raise


def convert_to_solar_permit_data(raw_data: Dict) -> Optional[Dict]:
    """
    공공데이터포털 JSON 데이터를 solar_permits 테이블 스키마에 맞게 변환

    API 필드명:
    - solarGenFcltNm: 태양광발전시설명
    - lctnRoadNmAddr: 소재지도로명주소
    - lctnLotnoAddr: 소재지지번주소
    - latitude: 위도
    - longitude: 경도
    - instlDtlPstnSeNm: 설치상세위치구분명
    - oprtngSttsSeNm: 가동상태구분명
    - capa: 설비용량(kW)
    - splyVolt: 공급전압(V)
    - freq: 주파수(Hz)
    - instlYr: 설치연도
    - instlArea: 설치면적
    - detlsUsg: 세부용도
    - prmsnYmd: 허가일자
    - prmsnInst: 허가기관
    - insttCode: 기관코드
    - insttNm: 기관명
    - crtrYmd: 데이터기준일자
    """
    try:
        # 필수 필드: facility_name
        facility_name = raw_data.get("solarGenFcltNm", "").strip()
        if not facility_name:
            logger.warning(f"시설명이 없는 데이터: {raw_data}")
            return None

        # 위도/경도 파싱
        latitude = None
        longitude = None
        try:
            lat_str = str(raw_data.get("latitude", "")).strip()
            lng_str = str(raw_data.get("longitude", "")).strip()
            if lat_str and lat_str != "":
                latitude = float(lat_str)
            if lng_str and lng_str != "":
                longitude = float(lng_str)
        except (ValueError, TypeError):
            pass

        # 용량 파싱
        capacity = None
        try:
            capa_str = str(raw_data.get("capa", "")).strip()
            if capa_str and capa_str != "":
                capacity = float(capa_str)
        except (ValueError, TypeError):
            pass

        return {
            "facility_name": facility_name,
            "road_address": raw_data.get("lctnRoadNmAddr", "").strip() or None,
            "lot_address": raw_data.get("lctnLotnoAddr", "").strip() or None,
            "latitude": latitude,
            "longitude": longitude,
            "installation_detail_position": raw_data.get("instlDtlPstnSeNm", "").strip() or None,
            "operation_status": raw_data.get("oprtngSttsSeNm", "").strip() or None,
            "capacity": capacity,
            "supply_voltage": raw_data.get("splyVolt", "").strip() or None,
            "frequency": raw_data.get("freq", "").strip() or None,
            "installation_year": raw_data.get("instlYr", "").strip() or None,
            "installation_area": raw_data.get("instlArea", "").strip() or None,
            "detail_usage": raw_data.get("detlsUsg", "").strip() or None,
            "permission_date": raw_data.get("prmsnYmd", "").strip() or None,
            "permission_institution": raw_data.get("prmsnInst", "").strip() or None,
            "institution_code": raw_data.get("insttCode", "").strip() or None,
            "institution_name": raw_data.get("insttNm", "").strip() or None,
            "criteria_date": raw_data.get("crtrYmd", "").strip() or None,
            "raw_data": json.dumps(raw_data, ensure_ascii=False)  # JSONB로 저장
        }

    except Exception as e:
        logger.error(f"데이터 변환 오류: {raw_data.get('solarGenFcltNm', 'Unknown')}: {e}")
        return None


_INSERT_SQL = text("""
    INSERT INTO solar_permits (
        facility_name, road_address, lot_address, latitude, longitude,
        installation_detail_position, operation_status, capacity,
        supply_voltage, frequency, installation_year, installation_area,
        detail_usage, permission_date, permission_institution,
        institution_code, institution_name, criteria_date, raw_data,
        last_synced_at
    ) VALUES (
        :facility_name, :road_address, :lot_address, :latitude, :longitude,
        :installation_detail_position, :operation_status, :capacity,
        :supply_voltage, :frequency, :installation_year, :installation_area,
        :detail_usage, :permission_date, :permission_institution,
        :institution_code, :institution_name, :criteria_date, CAST(:raw_data AS jsonb),
        NOW()
    )
""")


def import_solar_permits_from_json(db: Session, json_file_path: str, replace: bool = True) -> Dict:
    """JSON 파일에서 태양광 허가 데이터를 읽어서 DB에 저장한다 (멱등).

    이 데이터는 공공데이터포털의 **전체 스냅샷**이므로, 재실행 시 append가 아니라
    전량 교체(replace)가 올바른 의미론이다. 구 구현은 dedup 없는 blind INSERT라
    재임포트/주간 동기화마다 11만 건이 통째로 중복 적재되던 버그가 있었다.

    replace=True(기본): 기존 solar_permits를 삭제한 뒤 새로 적재한다.
    - 삭제와 적재를 **단일 트랜잭션**으로 묶어, 실패 시 롤백으로 기존 데이터가
      온전히 보존되고(빈 테이블로 남지 않음), 성공 시에만 원자적으로 교체된다.
    - `panel_permit_matches`가 solar_permits를 ON DELETE CASCADE로 참조하므로
      삭제 시 매칭도 함께 지워진다 — 호출부(동기화 태스크)가 적재 후 재매칭
      (batch_match_panels)으로 복구할 책임을 진다.
    """
    try:
        logger.info(f"JSON 파일 읽기: {json_file_path}")
        raw_data_list = parse_json_file(json_file_path)
        logger.info(f"총 {len(raw_data_list)}건의 데이터 발견")

        # 1) 데이터 변환(개별 실패는 건너뜀) — DB에 손대기 전에 먼저 전량 변환
        rows = []
        failed_count = 0
        for idx, raw_data in enumerate(raw_data_list, 1):
            permit_data = convert_to_solar_permit_data(raw_data)
            if not permit_data:
                failed_count += 1
                continue
            rows.append(permit_data)

        # 2) 단일 트랜잭션: (replace면) 전량 삭제 → 전량 적재 → commit.
        #    중간 커밋을 하지 않으므로 리더는 커밋 전까지 기존 스냅샷을 계속 본다.
        #    단, 개별 행 삽입은 SAVEPOINT(begin_nested)로 감싸 numeric overflow 등
        #    이상값 한 행이 동기화 전체를 무너뜨리지 않게 한다(공공데이터 품질 방어).
        synced_count = 0
        try:
            if replace:
                deleted = db.execute(text("DELETE FROM solar_permits")).rowcount
                logger.info(f"기존 데이터 {deleted}건 삭제(전량 교체) — 매칭은 CASCADE로 함께 삭제, 적재 후 재매칭 필요")

            for i in range(0, len(rows), 500):
                batch = rows[i:i + 500]
                sp = db.begin_nested()  # 배치 SAVEPOINT
                try:
                    for data in batch:
                        db.execute(_INSERT_SQL, data)
                    sp.commit()
                    synced_count += len(batch)
                except Exception as e:
                    sp.rollback()
                    logger.warning(f"배치 삽입 실패({e}) — 행별 재시도로 이상값만 건너뜀")
                    for data in batch:
                        row_sp = db.begin_nested()
                        try:
                            db.execute(_INSERT_SQL, data)
                            row_sp.commit()
                            synced_count += 1
                        except Exception as row_e:
                            row_sp.rollback()
                            failed_count += 1
                            logger.warning(f"행 건너뜀({data.get('facility_name')}): {row_e}")
                logger.info(f"적재 중... {synced_count}/{len(rows)}건")

            db.commit()  # 외부 트랜잭션 커밋 — 여기서만 실제 교체 확정
        except Exception:
            db.rollback()  # 실패 시 기존 데이터 보존(빈 테이블로 남지 않음)
            raise

        logger.info(f"✅ Import 완료! 성공: {synced_count}건 / 실패(변환): {failed_count}건")

        return {
            "status": "success",
            "synced": synced_count,
            "failed": failed_count,
            "total": len(raw_data_list),
        }

    except Exception as e:
        logger.error(f"Import 실패: {e}")
        raise


def main():
    """메인 함수"""
    if len(sys.argv) < 2:
        print("사용법: python import_solar_permits_to_db.py <json_file_path>")
        print("\n예시:")
        print("  python backend/scripts/import_solar_permits_to_db.py data/solar_permits_20260103_142443.json")
        sys.exit(1)

    json_file_path = sys.argv[1]

    if not os.path.exists(json_file_path):
        logger.error(f"파일을 찾을 수 없습니다: {json_file_path}")
        sys.exit(1)

    db = SessionLocal()
    try:
        result = import_solar_permits_from_json(db, json_file_path)
        print(f"\n✅ 성공적으로 완료되었습니다!")
        print(f"   성공: {result['synced']}건")
        print(f"   실패: {result['failed']}건")
    except Exception as e:
        logger.error(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
