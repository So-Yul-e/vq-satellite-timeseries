"""한국 전체를 100개 그리드로 스캔하여 태양광 패널 탐지"""
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

# GEE 초기화
def init_gee():
    """Google Earth Engine 초기화"""
    try:
        service_account_key = '/app/gee-service-account.json'
        if os.path.exists(service_account_key):
            with open(service_account_key, 'r') as f:
                key_data = json.load(f)
                service_account_email = key_data.get('client_email')

            credentials = ee.ServiceAccountCredentials(
                email=service_account_email,
                key_file=service_account_key
            )
            ee.Initialize(credentials)
            print(f"✅ GEE 초기화 성공: {service_account_email}")
            return True
        else:
            ee.Initialize()
            print("✅ GEE 기본 인증 성공")
            return True
    except Exception as e:
        print(f"❌ GEE 초기화 실패: {e}")
        return False


# 데이터베이스 연결
def get_db_connection():
    """PostgreSQL 연결"""
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        database=os.getenv('POSTGRES_DB', 'vq_satellite'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD')
    )


def generate_korea_grid(grid_count=100):
    """
    한국 전체를 그리드로 분할

    Args:
        grid_count: 생성할 그리드 개수 (기본값: 100)

    Returns:
        List[Dict]: 그리드 정보 (위도, 경도, 이름)
    """
    # 한국 영토 범위 (대략적)
    # 위도: 33.0° ~ 38.5° (약 5.5도)
    # 경도: 124.5° ~ 131.5° (약 7.0도)

    lat_min, lat_max = 33.0, 38.5
    lon_min, lon_max = 124.5, 131.5

    # 그리드 크기 계산 (10x10 그리드)
    grid_rows = 10
    grid_cols = 10

    lat_step = (lat_max - lat_min) / grid_rows
    lon_step = (lon_max - lon_min) / grid_cols

    grids = []
    grid_id = 1

    for row in range(grid_rows):
        for col in range(grid_cols):
            # 그리드 중심 좌표 계산
            lat = lat_min + (row + 0.5) * lat_step
            lon = lon_min + (col + 0.5) * lon_step

            grids.append({
                "id": grid_id,
                "name": f"Grid-{grid_id:03d} (R{row+1}C{col+1})",
                "lat": lat,
                "lon": lon,
                "row": row,
                "col": col
            })
            grid_id += 1

    return grids


def download_satellite_image(latitude, longitude, buffer_km=2.5):
    """GEE에서 위성 영상 다운로드 (그리드용 - 더 작은 영역)"""
    try:
        # 관심 지역 설정
        point = ee.Geometry.Point([longitude, latitude])
        aoi = point.buffer(buffer_km * 1000)

        # 최근 6개월 영상
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')

        # Sentinel-2 영상 가져오기
        collection = (
            ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(aoi)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))  # 구름 30% 이하
            .sort('CLOUDY_PIXEL_PERCENTAGE')
        )

        count = collection.size().getInfo()
        if count == 0:
            return None

        # 가장 구름 적은 영상 선택
        image = collection.first()

        # RGB 영상으로 변환
        rgb = image.select(['B4', 'B3', 'B2'])

        # 썸네일 URL 생성 (고해상도)
        url = rgb.getThumbURL({
            'region': aoi.getInfo()['coordinates'],
            'dimensions': 1024,  # 1024x1024
            'format': 'jpg'
        })

        # 영상 다운로드
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            if response.status_code == 200:
                img = Image.open(io.BytesIO(response.content))
                return img, aoi
            else:
                return None

    except Exception as e:
        print(f"  ⚠️ 영상 다운로드 오류: {e}")
        return None


def detect_solar_panels(image, model, confidence_threshold=0.2):
    """YOLOv8로 태양광 패널 탐지"""
    try:
        # YOLOv8 추론
        results = model.predict(
            image,
            conf=confidence_threshold,  # 신뢰도 임계값 (0.2)
            iou=0.45,
            imgsz=640,
            verbose=False  # 로그 줄이기
        )

        detections = []
        if len(results) > 0:
            result = results[0]
            if result.masks is not None:
                # 세그멘테이션 결과 처리
                for i, (box, mask) in enumerate(zip(result.boxes, result.masks)):
                    conf = float(box.conf[0])

                    # 바운딩 박스 (xyxy 형식)
                    x1, y1, x2, y2 = box.xyxy[0].tolist()

                    # 마스크의 좌표 (픽셀)
                    mask_coords = mask.xy[0] if len(mask.xy) > 0 else None

                    detections.append({
                        'bbox': [x1, y1, x2, y2],
                        'mask': mask_coords.tolist() if mask_coords is not None else None,
                        'confidence': conf,
                        'class': int(box.cls[0])
                    })

        return detections

    except Exception as e:
        print(f"  ⚠️ 탐지 오류: {e}")
        return []


def pixel_to_geo(pixel_x, pixel_y, aoi, image_width, image_height):
    """픽셀 좌표를 지리 좌표로 변환"""
    # AOI의 경계 좌표
    coords = aoi.getInfo()['coordinates'][0]

    # 경계 박스 계산
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]

    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)

    # 픽셀 -> 지리 좌표 변환
    lon = min_lon + (pixel_x / image_width) * (max_lon - min_lon)
    lat = max_lat - (pixel_y / image_height) * (max_lat - min_lat)

    return lat, lon


def save_to_database(detections_with_coords, conn):
    """탐지 결과를 데이터베이스에 저장 (배치 방식)"""
    try:
        cursor = conn.cursor()

        # 새로운 탐지 결과 삽입
        insert_query = """
            INSERT INTO solar_panels
            (id, detection_id, latitude, longitude, area_m2, confidence, panel_count,
             status, is_illegal, description, detection_date, created_at)
            VALUES %s
            ON CONFLICT (detection_id) DO NOTHING
        """

        # 한국 육지 범위 (바다 필터링)
        KOREA_LAT_MIN = 33.5
        KOREA_LAT_MAX = 38.5
        KOREA_LON_MIN = 125.5
        KOREA_LON_MAX = 130.0
        MAX_AREA_M2 = 100000  # 100,000 m² (0.1 km²) 상한선

        values = []
        filtered_out = 0

        for det in detections_with_coords:
            # 육지 범위 체크 (바다 필터링)
            lat = det['latitude']
            lon = det['longitude']

            if not (KOREA_LAT_MIN <= lat <= KOREA_LAT_MAX and
                    KOREA_LON_MIN <= lon <= KOREA_LON_MAX):
                filtered_out += 1
                continue  # 바다 영역은 건너뛰기

            # 면적 추정 (bbox 기반, 매우 대략적)
            bbox = det['bbox']
            area_pixels = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            # 1024x1024 이미지가 약 2.5km x 2.5km 커버 (그리드 크기 조정)
            # 1 픽셀 ≈ (2500m / 1024)^2 ≈ 6.0 m^2
            area_m2 = area_pixels * 6.0

            # 면적 상한선 체크
            if area_m2 > MAX_AREA_M2:
                filtered_out += 1
                continue  # 비정상적으로 큰 면적은 건너뛰기

            panel_count = max(1, int(area_m2 / 10))  # 10m²당 1개 패널 가정

            now = datetime.now()
            detection_id = f"GRID{det['grid_id']:03d}-{det['idx']:04d}"

            values.append((
                str(uuid.uuid4()),  # UUID
                detection_id,
                lat,
                lon,
                area_m2,
                det['confidence'],
                panel_count,
                'detected',
                False,  # AI 탐지는 일단 합법으로 가정
                f"{det['grid_name']} AI 그리드 스캔",
                now,  # detection_date
                now   # created_at
            ))

        if filtered_out > 0:
            print(f"  ⚠️ 필터링됨: {filtered_out}개 (바다 또는 비정상 면적)")

        if values:
            execute_values(cursor, insert_query, values)
            conn.commit()

        cursor.close()
        return len(values)

    except Exception as e:
        print(f"  ⚠️ DB 저장 오류: {e}")
        conn.rollback()
        return 0


def scan_grid(grid, model, conn):
    """단일 그리드 스캔"""
    grid_id = grid['id']
    grid_name = grid['name']
    latitude = grid['lat']
    longitude = grid['lon']

    # 1. 위성 영상 다운로드
    result = download_satellite_image(latitude, longitude, buffer_km=2.5)

    if result is None:
        return 0, 0  # (탐지 개수, 저장 개수)

    image, aoi = result

    # 2. YOLOv8 탐지 (신뢰도 0.2)
    detections = detect_solar_panels(image, model, confidence_threshold=0.2)

    if len(detections) == 0:
        return 0, 0

    # 3. 픽셀 좌표를 지리 좌표로 변환
    detections_with_coords = []
    for idx, det in enumerate(detections):
        bbox = det['bbox']
        center_x = (bbox[0] + bbox[2]) / 2
        center_y = (bbox[1] + bbox[3]) / 2

        lat, lon = pixel_to_geo(
            center_x, center_y, aoi,
            image.width, image.height
        )

        detections_with_coords.append({
            **det,
            'latitude': lat,
            'longitude': lon,
            'grid_id': grid_id,
            'grid_name': grid_name,
            'idx': idx
        })

    # 4. 데이터베이스에 저장
    saved_count = save_to_database(detections_with_coords, conn)

    return len(detections), saved_count


def main():
    """메인 함수"""
    print("="*80)
    print("🌞 한국 전체 100개 그리드 태양광 패널 스캔 (신뢰도 0.2)")
    print("="*80)

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
        print("   먼저 download_yolov8_model.py를 실행하세요.")
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

    # 4. 한국 전체 100개 그리드 생성
    print("\n4️⃣ 한국 전체 100개 그리드 생성...")
    grids = generate_korea_grid(grid_count=100)
    print(f"✅ {len(grids)}개 그리드 생성 완료")
    print(f"   위도 범위: 33.0° ~ 38.5°")
    print(f"   경도 범위: 124.5° ~ 131.5°")

    # 5. 그리드 스캔 시작
    print("\n5️⃣ 그리드 스캔 시작...")
    print("="*80)

    total_detections = 0
    total_saved = 0
    successful_grids = 0
    start_time = time.time()

    for i, grid in enumerate(grids, 1):
        grid_name = grid['name']
        print(f"\n[{i}/100] {grid_name} ({grid['lat']:.3f}, {grid['lon']:.3f})...", end=" ")

        detected, saved = scan_grid(grid, model, conn)

        if detected > 0:
            print(f"✅ 탐지 {detected}개, 저장 {saved}개")
            total_detections += detected
            total_saved += saved
            successful_grids += 1
        else:
            print("⏭️")

        # API 제한 방지 (1초 대기)
        if i < len(grids):
            time.sleep(1)

        # 진행률 표시 (10개마다)
        if i % 10 == 0:
            elapsed = time.time() - start_time
            avg_time_per_grid = elapsed / i
            remaining_grids = len(grids) - i
            eta_seconds = avg_time_per_grid * remaining_grids
            eta_minutes = eta_seconds / 60

            print(f"\n📊 진행률: {i}/100 ({i}%) | "
                  f"탐지: {total_detections}개 | "
                  f"저장: {total_saved}개 | "
                  f"ETA: {eta_minutes:.1f}분")

    # 6. 완료
    elapsed = time.time() - start_time
    print("\n" + "="*80)
    print(f"🎉 한국 전체 그리드 스캔 완료!")
    print(f"   스캔한 그리드: {len(grids)}개")
    print(f"   성공한 그리드: {successful_grids}개")
    print(f"   총 탐지 개수: {total_detections}개")
    print(f"   DB 저장 개수: {total_saved}개")
    print(f"   소요 시간: {elapsed/60:.1f}분 ({elapsed:.1f}초)")
    print("="*80)

    conn.close()


if __name__ == "__main__":
    main()
