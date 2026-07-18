"""
위험도 평가 서비스 간단 테스트
pytest 없이 실행 가능
"""
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.dem_service import DEMService
from app.services.water_distance_service import WaterDistanceService
from app.services.protected_area_service import ProtectedAreaService
from app.services.ndvi_forest_service import NDVIForestService


def test_dem_service():
    """DEM 서비스 테스트"""
    print("\n" + "="*60)
    print("1. DEM 서비스 테스트 (경사도 및 표고)")
    print("="*60)

    dem_service = DEMService()

    # 테스트 위치 1: 한라산 (경사도가 높은 지역)
    print("\n📍 테스트 위치: 한라산 (33.362°N, 126.533°E)")
    hallasan_lat = 33.362
    hallasan_lon = 126.533

    try:
        # 경사도 계산
        slope = dem_service.get_slope_at_location(hallasan_lat, hallasan_lon, buffer_m=100)
        print(f"   ✅ 경사도: {slope:.2f}도")

        # 표고 계산
        elevation = dem_service.get_elevation_at_location(hallasan_lat, hallasan_lon)
        print(f"   ✅ 표고: {elevation:.2f}m")

        # 종합 지형 분석
        terrain = dem_service.get_terrain_analysis(hallasan_lat, hallasan_lon, buffer_m=200)
        print(f"   ✅ 지형 분석:")
        print(f"      - 평균 표고: {terrain['elevation_mean']:.2f}m")
        print(f"      - 최대 표고: {terrain['elevation_max']:.2f}m")
        print(f"      - 평균 경사도: {terrain['slope_mean']:.2f}도")
        print(f"      - 최대 경사도: {terrain['slope_max']:.2f}도")

        print("\n   ✅ DEM 서비스 테스트 성공!")

    except Exception as e:
        print(f"\n   ❌ 실패: {e}")
        import traceback
        traceback.print_exc()


def test_water_distance_service():
    """수계 거리 서비스 테스트"""
    print("\n" + "="*60)
    print("2. 수계 거리 서비스 테스트")
    print("="*60)

    water_service = WaterDistanceService()

    # 테스트 위치 1: 한강 근처
    print("\n📍 테스트 위치: 한강 근처 (37.5326°N, 126.9900°E)")
    hangang_lat = 37.5326
    hangang_lon = 126.9900

    try:
        # 수계 거리 계산
        distance = water_service.calculate_water_distance(
            hangang_lat, hangang_lon, search_radius_km=3.0
        )
        print(f"   ✅ 수계까지 거리: {distance:.2f}m ({distance/1000:.2f}km)")

        # 수계 정보 조회
        water_info = water_service.get_water_body_info(hangang_lat, hangang_lon, buffer_m=100)
        print(f"   ✅ 수계 정보:")
        print(f"      - 수계 근처 여부: {water_info['is_near_water']}")
        print(f"      - 수계 발생 빈도: {water_info['water_occurrence']:.2f}%")
        print(f"      - 수계 유형: {water_info['water_type']}")

        # 위험도 확인
        is_risky, dist = water_service.check_water_proximity_risk(
            hangang_lat, hangang_lon, risk_threshold_m=200
        )
        print(f"   ✅ 수질 위험도: {'위험' if is_risky else '안전'} (거리: {dist:.2f}m)")

        print("\n   ✅ 수계 거리 서비스 테스트 성공!")

    except Exception as e:
        print(f"\n   ❌ 실패: {e}")
        import traceback
        traceback.print_exc()


def test_protected_area_service():
    """보호구역 서비스 테스트"""
    print("\n" + "="*60)
    print("3. 보호구역 서비스 테스트")
    print("="*60)

    protected_service = ProtectedAreaService()

    # 테스트 위치 1: 설악산 국립공원
    print("\n📍 테스트 위치: 설악산 국립공원 (38.1198°N, 128.4655°E)")
    seoraksan_lat = 38.1198
    seoraksan_lon = 128.4655

    try:
        # 보호구역 침범 확인
        is_violated = protected_service.check_protected_area_violation(
            seoraksan_lat, seoraksan_lon, buffer_m=50
        )
        print(f"   ✅ 보호구역 침범 여부: {'침범' if is_violated else '안전'}")

        # 보호구역 정보 조회
        protected_info = protected_service.get_protected_area_info(
            seoraksan_lat, seoraksan_lon, buffer_m=100
        )
        print(f"   ✅ 보호구역 정보:")
        print(f"      - 보호구역 내 위치: {protected_info['is_protected']}")
        print(f"      - 보호구역 개수: {protected_info['count']}")
        if protected_info['areas']:
            for area in protected_info['areas'][:3]:  # 최대 3개만 출력
                print(f"      - {area['name']} ({area['type']})")

        # 한국 보호구역 검사
        korea_info = protected_service.check_korea_protected_areas(seoraksan_lat, seoraksan_lon)
        print(f"   ✅ 한국 보호구역: {korea_info}")

        # 보호 심각도 계산
        severity = protected_service.get_protection_severity(seoraksan_lat, seoraksan_lon)
        print(f"   ✅ 보호 심각도: {severity}/100")

        print("\n   ✅ 보호구역 서비스 테스트 성공!")

    except Exception as e:
        print(f"\n   ❌ 실패: {e}")
        import traceback
        traceback.print_exc()


def test_ndvi_forest_service():
    """NDVI 산림 서비스 테스트"""
    print("\n" + "="*60)
    print("4. NDVI 산림 서비스 테스트")
    print("="*60)

    ndvi_service = NDVIForestService()

    # 테스트 위치 1: 지리산 (산림 지역)
    print("\n📍 테스트 위치: 지리산 (35.3396°N, 127.7308°E)")
    jirisan_lat = 35.3396
    jirisan_lon = 127.7308

    try:
        # NDVI 계산
        ndvi = ndvi_service.calculate_ndvi_at_location(
            jirisan_lat, jirisan_lon, buffer_m=100
        )
        print(f"   ✅ NDVI 값: {ndvi:.4f}")
        print(f"      (NDVI 범위: -1.0 ~ 1.0, 높을수록 식생이 울창함)")

        # 산림 분류
        forest_class = ndvi_service.get_forest_classification(jirisan_lat, jirisan_lon)
        print(f"   ✅ 산림 분류: {forest_class}")

        # 산림 훼손 면적 추정
        estimated_damage = ndvi_service.estimate_forest_damage_area(
            jirisan_lat, jirisan_lon, area_m2=1000
        )
        print(f"   ✅ 추정 산림 훼손 면적: {estimated_damage:.2f}m²")
        print(f"      (가정: 1000m² 패널 설치 시)")

        print("\n   ✅ NDVI 산림 서비스 테스트 성공!")

    except Exception as e:
        print(f"\n   ❌ 실패: {e}")
        import traceback
        traceback.print_exc()


def main():
    """메인 테스트 실행"""
    print("\n" + "🚀"*30)
    print("위험도 평가 시스템 서비스 테스트")
    print("🚀"*30)

    print("\n⚠️ 주의: 이 테스트는 Google Earth Engine 인증이 필요합니다.")
    print("   GEE 서비스 계정 키 파일(gee-service-account.json)이 필요합니다.")
    print("   또는 `earthengine authenticate` 명령으로 인증해야 합니다.\n")

    # Earth Engine 초기화 확인
    try:
        import ee
        ee.Initialize()
        print("✅ Google Earth Engine 초기화 성공!\n")
    except Exception as e:
        print(f"❌ Google Earth Engine 초기화 실패: {e}")
        print("   테스트를 계속 진행하지만 오류가 발생할 수 있습니다.\n")

    # 각 서비스 테스트 실행
    test_dem_service()
    test_water_distance_service()
    test_protected_area_service()
    test_ndvi_forest_service()

    print("\n" + "="*60)
    print("🎉 모든 테스트 완료!")
    print("="*60)
    print("\n💡 참고:")
    print("   - 각 서비스는 Google Earth Engine API를 사용합니다")
    print("   - 네트워크 연결과 GEE 인증이 필요합니다")
    print("   - 일부 테스트는 시간이 걸릴 수 있습니다 (5-10초)")
    print()


if __name__ == "__main__":
    main()
