"""간단한 태양광 패널 탐지 및 DB 저장"""
import os
import sys
import uuid
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values

# 테스트 데이터 생성 (서울/경기 지역)
TEST_DETECTIONS = []

# 서울/경기 주요 지역에 임의 패널 생성
import random
regions = [
    {"name": "서울", "lat": 37.5665, "lon": 126.9780},
    {"name": "경기 성남", "lat": 37.4201, "lon": 127.1262},
    {"name": "경기 화성", "lat": 37.1989, "lon": 126.8312},
    {"name": "경기 안성", "lat": 37.0079, "lon": 127.2797},
    {"name": "경기 여주", "lat": 37.2982, "lon": 127.6373},
]

for region in regions:
    # 각 지역당 20개씩 패널 생성
    for i in range(20):
        lat = region['lat'] + (random.random() - 0.5) * 0.1
        lon = region['lon'] + (random.random() - 0.5) * 0.1
        
        polygon = {
            "type": "Polygon",
            "coordinates": [[
                [lon, lat],
                [lon + 0.0005, lat],
                [lon + 0.0005, lat + 0.0005],
                [lon, lat + 0.0005],
                [lon, lat]
            ]]
        }
        
        TEST_DETECTIONS.append({
            'center_latitude': lat,
            'center_longitude': lon,
            'panel_polygon': polygon,
            'area_m2': random.uniform(100, 500),
            'detection_confidence': random.uniform(0.7, 0.95),
            'region': region['name']
        })

print(f"생성된 탐지 결과: {len(TEST_DETECTIONS)}개")

# DB 연결
try:
    conn = psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'vq_satellite'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD')
    )
    print("✅ DB 연결 성공")
except Exception as e:
    print(f"❌ DB 연결 실패: {e}")
    sys.exit(1)

# Satellite ID 가져오기
cursor = conn.cursor()
cursor.execute("SELECT id FROM satellites LIMIT 1")
satellite_row = cursor.fetchone()

if not satellite_row:
    print("❌ Satellite 데이터가 없습니다")
    conn.close()
    sys.exit(1)

satellite_id = satellite_row[0]
print(f"Satellite ID: {satellite_id}")

# 데이터 삽입
insert_query = """
    INSERT INTO solar_panels (
        id, satellite_id, center_latitude, center_longitude,
        panel_polygon, area_m2, detection_confidence, status, created_at
    ) VALUES %s
"""

values = [
    (
        str(uuid.uuid4()),
        str(satellite_id),
        det['center_latitude'],
        det['center_longitude'],
        str(det['panel_polygon']).replace("'", '"'),  # JSON으로 변환
        det['area_m2'],
        det['detection_confidence'],
        'detected',
        datetime.now()
    )
    for det in TEST_DETECTIONS
]

try:
    execute_values(cursor, insert_query, values)
    conn.commit()
    print(f"✅ {len(values)}개 패널 데이터 삽입 완료!")
except Exception as e:
    print(f"❌ 삽입 실패: {e}")
    conn.rollback()
finally:
    cursor.close()
    conn.close()

print("\n✅ 완료! 이제 프론트엔드에서 확인해보세요.")
