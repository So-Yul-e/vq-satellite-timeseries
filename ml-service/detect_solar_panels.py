"""YOLOv8로 전국 태양광 패널 실시간 탐지"""
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


def download_satellite_image(latitude, longitude, buffer_km=5.0):
    """GEE에서 위성 영상 다운로드"""
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
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
            .sort('CLOUDY_PIXEL_PERCENTAGE')
        )

        count = collection.size().getInfo()
        if count == 0:
            print(f"  ⚠️ 영상 없음: ({latitude}, {longitude})")
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
                print(f"  ❌ 다운로드 실패: HTTP {response.status_code}")
                return None

    except Exception as e:
        print(f"  ❌ 영상 다운로드 오류: {e}")
        return None


def detect_solar_panels(image, model):
    """YOLOv8로 태양광 패널 탐지"""
    try:
        # YOLOv8 추론
        results = model.predict(
            image,
            conf=0.3,  # 신뢰도 임계값
            iou=0.45,
            imgsz=640
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
        print(f"  ❌ 탐지 오류: {e}")
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
    """탐지 결과를 데이터베이스에 저장"""
    try:
        cursor = conn.cursor()

        # 기존 데이터 삭제 (새로운 스캔 결과로 대체)
        cursor.execute("DELETE FROM solar_panels WHERE description LIKE '%AI 탐지%'")

        # 새로운 탐지 결과 삽입
        insert_query = """
            INSERT INTO solar_panels
            (id, detection_id, latitude, longitude, area_m2, confidence, panel_count,
             status, is_illegal, description, detection_date, created_at)
            VALUES %s
        """

        values = []
        for idx, det in enumerate(detections_with_coords):
            # 면적 추정 (bbox 기반, 매우 대략적)
            bbox = det['bbox']
            area_pixels = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            # 1024x1024 이미지가 약 5km x 5km 커버
            # 1 픽셀 ≈ (5000m / 1024)^2 ≈ 23.8 m^2
            area_m2 = area_pixels * 23.8

            panel_count = int(area_m2 / 10)  # 10m²당 1개 패널 가정

            now = datetime.now()
            values.append((
                str(uuid.uuid4()),  # UUID 문자열로 변환
                f"AI{idx+1:06d}",
                det['latitude'],
                det['longitude'],
                area_m2,
                det['confidence'],
                panel_count,
                'detected',
                False,  # AI 탐지는 일단 합법으로 가정
                f"{det['region']} AI 탐지",
                now,  # detection_date
                now   # created_at
            ))

        if values:
            execute_values(cursor, insert_query, values)
            conn.commit()
            print(f"  ✅ {len(values)}개 탐지 결과 저장 완료")

        cursor.close()

    except Exception as e:
        print(f"  ❌ DB 저장 오류: {e}")
        conn.rollback()


def scan_region(region_name, latitude, longitude, model, conn):
    """특정 지역 스캔"""
    print(f"\n📍 {region_name} 스캔 시작...")
    print(f"   위치: ({latitude}, {longitude})")

    # 1. 위성 영상 다운로드
    print(f"  🛰️  위성 영상 다운로드 중...")
    result = download_satellite_image(latitude, longitude, buffer_km=5.0)

    if result is None:
        print(f"  ⏭️  {region_name} 건너뛰기\n")
        return 0

    image, aoi = result
    print(f"  ✅ 영상 다운로드 완료 ({image.size})")

    # 2. YOLOv8 탐지
    print(f"  🤖 AI 탐지 중...")
    detections = detect_solar_panels(image, model)
    print(f"  ✅ {len(detections)}개 태양광 패널 탐지")

    if len(detections) == 0:
        print(f"  ⏭️  탐지 결과 없음\n")
        return 0

    # 3. 픽셀 좌표를 지리 좌표로 변환
    print(f"  🗺️  좌표 변환 중...")
    detections_with_coords = []
    for det in detections:
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
            'region': region_name
        })

    # 4. 데이터베이스에 저장
    print(f"  💾 데이터베이스 저장 중...")
    save_to_database(detections_with_coords, conn)

    print(f"✅ {region_name} 스캔 완료!\n")
    return len(detections)


def main():
    """메인 함수"""
    print("="*60)
    print("🌞 YOLOv8 전국 태양광 패널 탐지 시스템")
    print("="*60)

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
    print("="*60)

    # 주요 태양광 밀집 지역 (샘플 데이터와 동일)
    SCAN_REGIONS = [
        {"name": "전남 해남", "lat": 34.5700, "lon": 126.5900},
        {"name": "전남 영암", "lat": 34.8004, "lon": 126.6964},
        {"name": "전남 무안", "lat": 34.9906, "lon": 126.4820},
        {"name": "강원 영월", "lat": 37.1830, "lon": 128.4600},
        {"name": "강원 정선", "lat": 37.3807, "lon": 128.6610},
        {"name": "충북 청주", "lat": 36.6420, "lon": 127.4890},
        {"name": "충남 당진", "lat": 36.8926, "lon": 126.6478},
        {"name": "경북 영천", "lat": 35.9733, "lon": 128.9386},
        {"name": "경북 상주", "lat": 36.4110, "lon": 128.1590},
        {"name": "경남 산청", "lat": 35.4150, "lon": 127.8734},
        {"name": "전북 고창", "lat": 35.4344, "lon": 126.7017},
        {"name": "세종", "lat": 36.4800, "lon": 127.2890},
    ]

    total_detections = 0
    start_time = time.time()

    for region in SCAN_REGIONS:
        count = scan_region(
            region['name'],
            region['lat'],
            region['lon'],
            model,
            conn
        )
        total_detections += count

        # API 제한 방지 (2초 대기)
        time.sleep(2)

    # 5. 완료
    elapsed = time.time() - start_time
    print("="*60)
    print(f"🎉 전국 스캔 완료!")
    print(f"   총 탐지 개수: {total_detections}개")
    print(f"   소요 시간: {elapsed:.1f}초")
    print("="*60)

    conn.close()


if __name__ == "__main__":
    main()
