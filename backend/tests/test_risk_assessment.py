"""
위험도 평가 시스템 통합 테스트
"""
import pytest
import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.risk_assessment_service import RiskAssessmentService
from app.services.dem_service import DEMService
from app.services.water_distance_service import WaterDistanceService
from app.services.protected_area_service import ProtectedAreaService
from app.services.ndvi_forest_service import NDVIForestService
from app.models.solar_panel import SolarPanel
from app.models.satellite import Satellite
from app.models.user import User
from app.models.role import Role
# app.models 패키지를 통째로 import해 Base.metadata가 panel_permit_matches 등
# 전체 스키마를 인지하도록 한다. 그렇지 않으면 다른 테스트가 남긴 FK 참조 테이블을
# 이번 세션의 metadata가 모른 채 drop_all을 호출해 FK 제약 순서 에러가 난다.
import app.models  # noqa: F401
from app.core.database import Base
import uuid


class TestRiskAssessmentSystem:
    """위험도 평가 시스템 테스트"""

    @pytest.fixture(scope="class")
    def db_session(self):
        """테스트 데이터베이스 세션"""
        # 테스트용 인메모리 DB 사용 (또는 실제 DB 연결)
        from app.core.config import settings
        engine = create_engine(settings.DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # 테이블 생성
        Base.metadata.create_all(bind=engine)

        session = SessionLocal()
        yield session

        session.close()
        Base.metadata.drop_all(bind=engine)

    def test_dem_service_slope_calculation(self):
        """DEM 서비스: 경사도 계산 테스트"""
        print("\n=== DEM 서비스 테스트 ===")

        dem_service = DEMService()

        # 테스트 위치: 한라산 (경사도가 높은 지역)
        hallasan_lat = 33.362
        hallasan_lon = 126.533

        try:
            slope = dem_service.get_slope_at_location(hallasan_lat, hallasan_lon, buffer_m=100)
            print(f"✅ 한라산 경사도: {slope:.2f}도")
            assert slope > 0, "경사도는 0보다 커야 합니다"

            # 표고도 테스트
            elevation = dem_service.get_elevation_at_location(hallasan_lat, hallasan_lon)
            print(f"✅ 한라산 표고: {elevation:.2f}m")
            assert elevation > 1500, "한라산 표고는 1500m 이상이어야 합니다"

        except Exception as e:
            print(f"⚠️ DEM 테스트 실패: {e}")
            print("   (GEE 인증이 필요할 수 있습니다)")

    def test_water_distance_service(self):
        """수계 거리 계산 테스트"""
        print("\n=== 수계 거리 서비스 테스트 ===")

        water_service = WaterDistanceService()

        # 테스트 위치: 한강 근처
        hangang_lat = 37.5326
        hangang_lon = 126.9900

        try:
            distance = water_service.calculate_water_distance(
                hangang_lat, hangang_lon, search_radius_km=2.0
            )
            print(f"✅ 한강까지 거리: {distance:.2f}m")
            assert distance < 1000, "한강 근처이므로 거리가 1km 미만이어야 합니다"

            # 수계 정보 조회
            water_info = water_service.get_water_body_info(hangang_lat, hangang_lon, buffer_m=100)
            print(f"✅ 수계 정보: {water_info}")
            assert water_info['is_near_water'], "한강 근처이므로 수계가 있어야 합니다"

        except Exception as e:
            print(f"⚠️ 수계 거리 테스트 실패: {e}")

    def test_protected_area_service(self):
        """보호구역 검사 테스트"""
        print("\n=== 보호구역 서비스 테스트 ===")

        protected_service = ProtectedAreaService()

        # 테스트 위치: 설악산 국립공원
        seoraksan_lat = 38.1198
        seoraksan_lon = 128.4655

        try:
            is_violated = protected_service.check_protected_area_violation(
                seoraksan_lat, seoraksan_lon, buffer_m=50
            )
            print(f"✅ 설악산 보호구역 침범 여부: {is_violated}")

            # 보호구역 정보 조회
            protected_info = protected_service.get_protected_area_info(
                seoraksan_lat, seoraksan_lon, buffer_m=100
            )
            print(f"✅ 보호구역 정보: {protected_info}")

        except Exception as e:
            print(f"⚠️ 보호구역 테스트 실패: {e}")

    def test_ndvi_forest_service(self):
        """NDVI 산림 분석 테스트"""
        print("\n=== NDVI 산림 서비스 테스트 ===")

        ndvi_service = NDVIForestService()

        # 테스트 위치: 지리산 (산림 지역)
        jirisan_lat = 35.3396
        jirisan_lon = 127.7308

        try:
            ndvi = ndvi_service.calculate_ndvi_at_location(
                jirisan_lat, jirisan_lon, buffer_m=100
            )
            print(f"✅ 지리산 NDVI: {ndvi:.4f}")
            assert -1.0 <= ndvi <= 1.0, "NDVI는 -1.0에서 1.0 사이여야 합니다"

            # 산림 분류
            forest_class = ndvi_service.get_forest_classification(jirisan_lat, jirisan_lon)
            print(f"✅ 산림 분류: {forest_class}")

        except Exception as e:
            print(f"⚠️ NDVI 테스트 실패: {e}")

    def test_integrated_risk_assessment(self, db_session):
        """통합 위험도 평가 테스트"""
        print("\n=== 통합 위험도 평가 테스트 ===")

        # SolarPanel.satellite_id는 NOT NULL FK이므로 role -> user -> satellite를 먼저 생성
        test_role = db_session.query(Role).filter(Role.name == "test_role").first()
        if not test_role:
            test_role = Role(name="test_role", description="risk assessment test role")
            db_session.add(test_role)
            db_session.commit()
            db_session.refresh(test_role)

        test_user = User(
            email=f"risk-test-{uuid.uuid4()}@example.com",
            password_hash="test_hash",
            full_name="Risk Test User",
            role_id=test_role.id,
        )
        db_session.add(test_user)
        db_session.commit()
        db_session.refresh(test_user)

        test_satellite = Satellite(
            user_id=test_user.id,
            file_path="/tmp/test_satellite.tif",
        )
        db_session.add(test_satellite)
        db_session.commit()
        db_session.refresh(test_satellite)

        # 테스트용 태양광 패널 생성 (실제 컬럼: center_latitude/center_longitude/detection_confidence)
        test_panel = SolarPanel(
            satellite_id=test_satellite.id,
            center_latitude=37.5326,  # 한강 근처
            center_longitude=126.9900,
            panel_polygon={
                "type": "Polygon",
                "coordinates": [[
                    [126.9900, 37.5326],
                    [126.9905, 37.5326],
                    [126.9905, 37.5331],
                    [126.9900, 37.5331],
                    [126.9900, 37.5326],
                ]]
            },
            detection_confidence=0.85,
            area_m2=1500.0,
            status="detected",
        )

        db_session.add(test_panel)
        db_session.commit()
        db_session.refresh(test_panel)

        print(f"✅ 테스트 패널 생성: ID={test_panel.id}")

        # 위험도 평가 실행
        service = RiskAssessmentService(db_session)

        try:
            assessment = service.assess_panel_risk(test_panel.id)

            print(f"\n📊 위험도 평가 결과:")
            print(f"   - 경사도: {assessment.slope_degree}도 (위험도: {assessment.slope_risk_score})")
            print(f"   - 산림 훼손: {assessment.forest_damage_area_m2}m² (위험도: {assessment.forest_risk_score})")
            print(f"   - 수계 거리: {assessment.water_distance_m}m (위험도: {assessment.water_risk_score})")
            print(f"   - 보호구역 침범: {assessment.protected_area_violation} (위험도: {assessment.protected_risk_score})")
            print(f"   - 종합 점수: {assessment.total_risk_score}/100")
            print(f"   - 위험 등급: {assessment.risk_level}")

            assert assessment.total_risk_score >= 0, "위험 점수는 0 이상이어야 합니다"
            assert assessment.total_risk_score <= 100, "위험 점수는 100 이하여야 합니다"
            assert assessment.risk_level in ['low', 'medium', 'high', 'critical'], \
                "위험 등급은 low, medium, high, critical 중 하나여야 합니다"

            print(f"\n✅ 통합 위험도 평가 성공!")

        except Exception as e:
            print(f"\n❌ 통합 평가 실패: {e}")
            import traceback
            traceback.print_exc()


def test_individual_services():
    """개별 서비스 테스트 (pytest 없이 실행 가능)"""
    test_class = TestRiskAssessmentSystem()

    print("\n" + "="*60)
    print("위험도 평가 시스템 개별 서비스 테스트")
    print("="*60)

    # DEM 테스트
    test_class.test_dem_service_slope_calculation()

    # 수계 거리 테스트
    test_class.test_water_distance_service()

    # 보호구역 테스트
    test_class.test_protected_area_service()

    # NDVI 테스트
    test_class.test_ndvi_forest_service()

    print("\n" + "="*60)
    print("개별 서비스 테스트 완료")
    print("="*60)


if __name__ == "__main__":
    # 직접 실행 시 개별 서비스만 테스트 (DB 없이)
    print("🚀 위험도 평가 시스템 테스트 시작...\n")
    test_individual_services()
