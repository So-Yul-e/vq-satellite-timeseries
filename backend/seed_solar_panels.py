"""전국 태양광 패널 샘플 데이터 생성"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

from app.core.database import SessionLocal
from app.models.solar_panel import SolarPanel
import random
from datetime import datetime, timedelta

# 한국 주요 태양광 밀집 지역
SOLAR_REGIONS = [
    {"name": "전남 해남", "lat": 34.5700, "lon": 126.5900, "density": 50},
    {"name": "전남 영암", "lat": 34.8004, "lon": 126.6964, "density": 40},
    {"name": "전남 무안", "lat": 34.9906, "lon": 126.4820, "density": 35},
    {"name": "강원 영월", "lat": 37.1830, "lon": 128.4600, "density": 30},
    {"name": "강원 정선", "lat": 37.3807, "lon": 128.6610, "density": 25},
    {"name": "충북 청주", "lat": 36.6420, "lon": 127.4890, "density": 30},
    {"name": "충남 당진", "lat": 36.8926, "lon": 126.6478, "density": 35},
    {"name": "경북 영천", "lat": 35.9733, "lon": 128.9386, "density": 28},
    {"name": "경북 상주", "lat": 36.4110, "lon": 128.1590, "density": 25},
    {"name": "경남 산청", "lat": 35.4150, "lon": 127.8734, "density": 22},
    {"name": "전북 고창", "lat": 35.4344, "lon": 126.7017, "density": 30},
    {"name": "세종", "lat": 36.4800, "lon": 127.2890, "density": 20},
]


def generate_sample_panels(num_panels=500):
    """샘플 태양광 패널 데이터 생성"""
    db = SessionLocal()

    try:
        # AI 탐지 데이터는 보존하고 샘플 데이터만 삭제
        print("Clearing existing sample data (preserving AI detections)...")
        db.query(SolarPanel).filter(
            SolarPanel.description.like('%샘플 데이터%')
        ).delete(synchronize_session=False)
        db.commit()

        panels_created = 0

        for region in SOLAR_REGIONS:
            region_panels = int(region["density"])

            for i in range(region_panels):
                # 지역 중심으로부터 랜덤한 위치 (반경 ~20km)
                lat_offset = random.uniform(-0.15, 0.15)
                lon_offset = random.uniform(-0.15, 0.15)

                latitude = region["lat"] + lat_offset
                longitude = region["lon"] + lon_offset

                # 패널 정보
                area_m2 = random.uniform(50, 500)  # 50~500m²
                confidence = random.uniform(0.7, 0.99)
                panel_count = int(area_m2 / 10)  # 대략 10m²당 1개 패널

                # 불법 여부 (10% 확률)
                is_illegal = random.random() < 0.1

                # 상태
                if is_illegal:
                    status = "illegal"
                else:
                    status = random.choice(["detected", "verified", "legal"])

                # 탐지 날짜 (최근 1년)
                days_ago = random.randint(0, 365)
                detection_date = datetime.utcnow() - timedelta(days=days_ago)

                panel = SolarPanel(
                    detection_id=f"SP{panels_created + 1:06d}",
                    latitude=latitude,
                    longitude=longitude,
                    area_m2=area_m2,
                    confidence=confidence,
                    panel_count=panel_count,
                    status=status,
                    is_illegal=is_illegal,
                    description=f"{region['name']} 샘플 데이터",
                    detection_date=detection_date,
                    metadata_json={
                        "region": region["name"],
                        "method": "Sample Data"
                    }
                )

                db.add(panel)
                panels_created += 1

            print(f"✓ {region['name']}: {region_panels} panels created")

        db.commit()

        print(f"\n{'='*60}")
        print(f"Total panels created: {panels_created}")
        print(f"{'='*60}\n")

        # 통계
        total = db.query(SolarPanel).count()
        illegal = db.query(SolarPanel).filter(SolarPanel.is_illegal == True).count()

        print(f"Database Statistics:")
        print(f"  Total Panels: {total}")
        print(f"  Illegal Panels: {illegal}")
        print(f"  Legal Panels: {total - illegal}")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()

    finally:
        db.close()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Generating Sample Solar Panel Data")
    print("="*60 + "\n")

    generate_sample_panels()

    print("\n✅ Sample data generation completed!")
    print("\nYou can now test the API:")
    print("  GET  http://localhost:8000/api/solar-panels/all")
    print("  GET  http://localhost:8000/api/solar-panels/statistics")
    print("  GET  http://localhost:8000/api/solar-panels/heatmap")
    print()
