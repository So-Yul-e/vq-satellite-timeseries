"""
YOLOv8 개선 버전 태양광 패널 탐지
- 하이퍼파라미터 최적화
- 후처리 필터 추가
- 신뢰도 기반 품질 관리
"""
import ee
import os
import sys
from pathlib import Path
from ultralytics import YOLO
from datetime import datetime, timedelta
import httpx
from PIL import Image
import io
import json
import psycopg2
from psycopg2.extras import execute_values
import time
import uuid
import numpy as np

# 기존 함수들 임포트
from detect_solar_panels import init_gee, get_db_connection, download_satellite_image, pixel_to_geo


def detect_solar_panels_improved(image, model, conf_threshold=0.25, iou_threshold=0.45):
    """
    개선된 YOLOv8 태양광 패널 탐지

    개선사항:
    1. 낮은 신뢰도 임계값으로 더 많이 탐지
    2. 후처리 필터로 오탐지 제거
    3. 품질 점수 계산

    Args:
        image: PIL Image 객체
        model: YOLOv8 모델
        conf_threshold: 신뢰도 임계값 (낮을수록 더 많이 탐지)
        iou_threshold: IoU 임계값

    Returns:
        탐지 결과 리스트
    """
    try:
        # YOLOv8 추론 (더 낮은 임계값 사용)
        results = model.predict(
            image,
            conf=conf_threshold,  # 0.25로 낮춰서 더 많이 탐지
            iou=iou_threshold,
            imgsz=640,  # 필요시 1024로 증가 가능
            verbose=False
        )

        detections = []
        if len(results) > 0:
            result = results[0]
            if result.masks is not None:
                # 세그멘테이션 결과 처리
                for i, (box, mask) in enumerate(zip(result.boxes, result.masks)):
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()

                    # 마스크 좌표
                    mask_coords = mask.xy[0] if len(mask.xy) > 0 else None

                    # 기본 정보
                    det = {
                        'bbox': [x1, y1, x2, y2],
                        'mask': mask_coords.tolist() if mask_coords is not None else None,
                        'confidence': conf,
                        'class': int(box.cls[0]),
                        'area_pixels': (x2 - x1) * (y2 - y1)
                    }

                    # 품질 점수 계산
                    det['quality_score'] = calculate_quality_score(det)

                    detections.append(det)

            elif result.boxes is not None:
                # 바운딩 박스만 있는 경우
                for i, box in enumerate(result.boxes):
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()

                    det = {
                        'bbox': [x1, y1, x2, y2],
                        'mask': None,
                        'confidence': conf,
                        'class': int(box.cls[0]),
                        'area_pixels': (x2 - x1) * (y2 - y1)
                    }

                    det['quality_score'] = calculate_quality_score(det)
                    detections.append(det)

        # 후처리 필터 적용
        filtered_detections = apply_post_filters(detections, image.size)

        return filtered_detections

    except Exception as e:
        print(f"  ❌ 탐지 오류: {e}")
        return []


def calculate_quality_score(detection: dict) -> float:
    """
    탐지 결과의 품질 점수 계산

    고려 요소:
    1. 신뢰도
    2. 바운딩 박스 크기 (너무 작거나 크면 감점)
    3. 종횡비 (직사각형에 가까울수록 가점)

    Returns:
        품질 점수 (0-100)
    """
    # 신뢰도 점수 (0-50점)
    confidence_score = detection['confidence'] * 50

    # 면적 점수 (0-25점)
    # 적정 면적: 500-10000 픽셀
    area = detection['area_pixels']
    if 500 <= area <= 10000:
        area_score = 25
    elif 200 <= area < 500 or 10000 < area <= 20000:
        area_score = 15
    elif 100 <= area < 200 or 20000 < area <= 50000:
        area_score = 5
    else:
        area_score = 0

    # 종횡비 점수 (0-25점)
    # 태양광 패널은 직사각형 (종횡비 0.5-3.0)
    bbox = detection['bbox']
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]

    if height > 0:
        aspect_ratio = width / height
        if 0.5 <= aspect_ratio <= 3.0:
            aspect_score = 25
        elif 0.3 <= aspect_ratio < 0.5 or 3.0 < aspect_ratio <= 5.0:
            aspect_score = 15
        else:
            aspect_score = 5
    else:
        aspect_score = 0

    total_score = confidence_score + area_score + aspect_score
    return total_score


def apply_post_filters(detections: list, image_size: tuple) -> list:
    """
    후처리 필터 적용

    필터:
    1. 최소/최대 면적 필터
    2. 종횡비 필터
    3. 품질 점수 필터
    4. 이미지 경계 필터

    Args:
        detections: 탐지 결과 리스트
        image_size: (width, height)

    Returns:
        필터링된 탐지 결과
    """
    filtered = []
    img_width, img_height = image_size

    for det in detections:
        # 1. 면적 필터 (100-50000 픽셀)
        area = det['area_pixels']
        if area < 100 or area > 50000:
            continue

        # 2. 종횡비 필터
        bbox = det['bbox']
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]

        if height > 0:
            aspect_ratio = width / height
            # 너무 찌그러진 형태는 제외
            if aspect_ratio < 0.2 or aspect_ratio > 10.0:
                continue
        else:
            continue

        # 3. 품질 점수 필터 (40점 이상)
        if det['quality_score'] < 40:
            continue

        # 4. 이미지 경계 필터
        # 경계에 걸친 탐지는 불완전할 수 있음
        margin = 10  # 픽셀
        if (bbox[0] < margin or bbox[1] < margin or
            bbox[2] > img_width - margin or bbox[3] > img_height - margin):
            # 경계 탐지는 신뢰도가 높을 때만 허용
            if det['confidence'] < 0.6:
                continue

        filtered.append(det)

    return filtered


def save_to_database_improved(detections_with_coords, conn):
    """
    개선된 데이터베이스 저장 (실제 solar_panels 스키마 기준)
    - solar_panels 테이블에는 metadata_json 컬럼이 없어 스키마 외 필드는 저장하지 않음
    """
    try:
        cursor = conn.cursor()

        # satellite_id는 NOT NULL FK (011 마이그레이션 기준)
        cursor.execute("SELECT id FROM satellites LIMIT 1")
        satellite_row = cursor.fetchone()
        if not satellite_row:
            print("  ❌ DB 저장 오류: satellites 테이블에 데이터가 없습니다")
            cursor.close()
            return
        satellite_id = satellite_row[0]

        # 새로운 탐지 결과 삽입 (실제 컬럼: satellite_id, center_latitude/longitude,
        # panel_polygon, detection_confidence 등)
        insert_query = """
            INSERT INTO solar_panels
            (id, satellite_id, center_latitude, center_longitude, panel_polygon,
             area_m2, detection_confidence, status, created_at, updated_at)
            VALUES %s
        """

        values = []
        for idx, det in enumerate(detections_with_coords):
            # 면적 추정
            bbox = det['bbox']
            area_pixels = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            area_m2 = area_pixels * 23.8  # 1 픽셀 ≈ 23.8 m²

            # NOTE: solar_panels 테이블에는 metadata_json 컬럼이 없음(011 마이그레이션 기준).
            # panel_count/is_illegal/description/region/quality_score 등 스키마 외 정보는
            # 현재 저장할 곳이 없어 유실됨 — 별도 확인 필요.

            now = datetime.now()
            values.append((
                str(uuid.uuid4()),
                str(satellite_id),
                det['latitude'],
                det['longitude'],
                json.dumps(det['polygon']),
                area_m2,
                det['confidence'],
                'detected',
                now,
                now
            ))

        if values:
            execute_values(cursor, insert_query, values)
            conn.commit()
            print(f"  ✅ {len(values)}개 탐지 결과 저장 완료")

        cursor.close()

    except Exception as e:
        print(f"  ❌ DB 저장 오류: {e}")
        conn.rollback()


def scan_region_improved(region_name, latitude, longitude, model, conn,
                         conf_threshold=0.25, quality_threshold=40):
    """
    개선된 지역 스캔

    Args:
        conf_threshold: 신뢰도 임계값
        quality_threshold: 품질 점수 임계값
    """
    print(f"\n📍 {region_name} 스캔 시작 (개선 모드)...")
    print(f"   위치: ({latitude}, {longitude})")
    print(f"   설정: conf={conf_threshold}, quality≥{quality_threshold}")

    # 1. 위성 영상 다운로드
    print(f"  🛰️  위성 영상 다운로드 중...")
    result = download_satellite_image(latitude, longitude, buffer_km=5.0)

    if result is None:
        print(f"  ⏭️  {region_name} 건너뛰기\n")
        return 0

    image, aoi = result
    print(f"  ✅ 영상 다운로드 완료 ({image.size})")

    # 2. 개선된 YOLOv8 탐지
    print(f"  🤖 AI 탐지 중 (개선 알고리즘)...")
    detections = detect_solar_panels_improved(
        image, model,
        conf_threshold=conf_threshold,
        iou_threshold=0.45
    )

    # 품질 점수로 필터링
    high_quality = [d for d in detections if d['quality_score'] >= quality_threshold]

    print(f"  ✅ 전체 탐지: {len(detections)}개")
    print(f"  ✅ 고품질 탐지: {len(high_quality)}개 (품질≥{quality_threshold})")

    if len(high_quality) == 0:
        print(f"  ⏭️  고품질 탐지 결과 없음\n")
        return 0

    # 품질 점수 통계
    avg_quality = np.mean([d['quality_score'] for d in high_quality])
    avg_conf = np.mean([d['confidence'] for d in high_quality])
    print(f"  📊 평균 품질: {avg_quality:.1f}점, 평균 신뢰도: {avg_conf:.2%}")

    # 3. 픽셀 좌표를 지리 좌표로 변환
    print(f"  🗺️  좌표 변환 중...")
    detections_with_coords = []
    for det in high_quality:
        bbox = det['bbox']
        center_x = (bbox[0] + bbox[2]) / 2
        center_y = (bbox[1] + bbox[3]) / 2

        lat, lon = pixel_to_geo(
            center_x, center_y, aoi,
            image.width, image.height
        )

        # panel_polygon(NOT NULL) 구성을 위해 bbox 4개 코너도 지리좌표로 변환
        corner_lat_tl, corner_lon_tl = pixel_to_geo(bbox[0], bbox[1], aoi, image.width, image.height)
        corner_lat_tr, corner_lon_tr = pixel_to_geo(bbox[2], bbox[1], aoi, image.width, image.height)
        corner_lat_br, corner_lon_br = pixel_to_geo(bbox[2], bbox[3], aoi, image.width, image.height)
        corner_lat_bl, corner_lon_bl = pixel_to_geo(bbox[0], bbox[3], aoi, image.width, image.height)
        polygon = {
            "type": "Polygon",
            "coordinates": [[
                [corner_lon_tl, corner_lat_tl],
                [corner_lon_tr, corner_lat_tr],
                [corner_lon_br, corner_lat_br],
                [corner_lon_bl, corner_lat_bl],
                [corner_lon_tl, corner_lat_tl],
            ]]
        }

        detections_with_coords.append({
            **det,
            'latitude': lat,
            'longitude': lon,
            'polygon': polygon,
            'region': region_name
        })

    # 4. 데이터베이스에 저장
    print(f"  💾 데이터베이스 저장 중...")
    save_to_database_improved(detections_with_coords, conn)

    print(f"✅ {region_name} 스캔 완료!\n")
    return len(high_quality)


def main():
    """메인 함수"""
    print("="*70)
    print("🌞 YOLOv8 전국 태양광 패널 탐지 시스템 (개선 버전)")
    print("="*70)
    print("\n개선사항:")
    print("  - 낮은 신뢰도 임계값으로 더 많이 탐지 (conf=0.25)")
    print("  - 후처리 필터로 오탐지 제거")
    print("  - 품질 점수 기반 필터링 (40점 이상)")
    print("  - 탐지 결과 품질 정보 저장")
    print("="*70)

    # 1. GEE 초기화
    print("\n1️⃣ Google Earth Engine 초기화...")
    if not init_gee():
        print("❌ GEE 초기화 실패. 종료합니다.")
        return

    # 2. YOLOv8 모델 로드
    print("\n2️⃣ YOLOv8 모델 로드...")
    model_path = "./models/yolov8_solar_panels.pt"
    if not os.path.exists(model_path):
        print(f"❌ 모델 파일을 찾을 수 없습니다: {model_path}")
        return

    model = YOLO(model_path)
    print(f"✅ 모델 로드 완료: {model_path}")

    # 3. 데이터베이스 연결
    print("\n3️⃣ 데이터베이스 연결...")
    try:
        conn = get_db_connection()
        print("✅ 데이터베이스 연결 성공")
    except Exception as e:
        print(f"❌ 데이터베이스 연결 실패: {e}")
        return

    # 4. 전국 주요 태양광 밀집 지역 스캔
    print("\n4️⃣ 전국 스캔 시작...")
    print("="*70)

    # 주요 태양광 밀집 지역
    SCAN_REGIONS = [
        {"name": "전남 해남", "lat": 34.5700, "lon": 126.5900},
        {"name": "전남 영암", "lat": 34.8004, "lon": 126.6964},
        {"name": "전남 무안", "lat": 34.9906, "lon": 126.4820},
        {"name": "강원 영월", "lat": 37.1830, "lon": 128.4600},
        {"name": "충남 당진", "lat": 36.8926, "lon": 126.6478},
    ]

    total_detections = 0
    start_time = time.time()

    for region in SCAN_REGIONS:
        count = scan_region_improved(
            region['name'],
            region['lat'],
            region['lon'],
            model,
            conn,
            conf_threshold=0.25,  # 낮은 임계값
            quality_threshold=40   # 품질 필터
        )
        total_detections += count

        # API 제한 방지
        time.sleep(2)

    # 5. 완료
    elapsed = time.time() - start_time
    print("="*70)
    print(f"🎉 전국 스캔 완료!")
    print(f"   총 탐지 개수: {total_detections}개 (고품질)")
    print(f"   소요 시간: {elapsed:.1f}초")
    print("="*70)

    conn.close()


if __name__ == "__main__":
    main()
