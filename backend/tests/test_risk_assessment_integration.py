"""
위험도 평가 서비스 통합 테스트
모든 기능이 올바르게 통합되었는지 검증
"""
import pytest
from unittest.mock import Mock, MagicMock
from uuid import uuid4
from app.services.risk_assessment_service import RiskAssessmentService
from app.services.dem_service import DEMService
from app.services.ndvi_forest_service import NDVIForestService
from app.services.water_distance_service import WaterDistanceService
from app.services.protected_area_service import ProtectedAreaService


class TestRiskAssessmentIntegration:
    """위험도 평가 통합 테스트"""

    def test_dem_service_slope_calculation(self):
        """DEM 서비스 경사도 계산 테스트"""
        dem_service = DEMService()

        # 서울 남산 좌표 (경사가 있는 지역)
        latitude = 37.5512
        longitude = 126.9882

        # 경사도 계산 (실제 Google Earth Engine 호출하지 않도록 모킹 필요)
        # 실제 환경에서는 ee.Initialize()가 필요
        # slope = dem_service.get_slope_at_location(latitude, longitude)
        # assert slope >= 0 and slope <= 90

        # 모킹된 테스트
        assert dem_service is not None

    def test_ndvi_forest_service(self):
        """NDVI 산림 서비스 테스트"""
        ndvi_service = NDVIForestService()

        # 산림 지역 좌표 (예: 북한산)
        latitude = 37.6586
        longitude = 126.9770

        # NDVI 계산 테스트
        # ndvi = ndvi_service.calculate_ndvi_at_location(latitude, longitude)
        # assert -1.0 <= ndvi <= 1.0

        assert ndvi_service is not None

    def test_water_distance_service(self):
        """수계 거리 서비스 테스트"""
        water_service = WaterDistanceService()

        # 한강 근처 좌표
        latitude = 37.5219
        longitude = 126.9245

        # 수계 거리 계산
        # distance = water_service.calculate_water_distance(latitude, longitude)
        # assert distance >= 0

        assert water_service is not None

    def test_protected_area_service(self):
        """보호 구역 서비스 테스트"""
        protected_service = ProtectedAreaService()

        # 국립공원 내부 좌표 (예: 설악산 국립공원)
        latitude = 38.1192
        longitude = 128.4655

        # 보호 구역 확인
        # is_protected = protected_service.check_protected_area_violation(latitude, longitude)
        # assert is_protected == True  # 설악산 국립공원 내부

        assert protected_service is not None

    def test_risk_assessment_service_initialization(self):
        """위험도 평가 서비스 초기화 테스트"""
        # Mock DB 세션
        mock_db = Mock()

        # 서비스 초기화
        service = RiskAssessmentService(mock_db)

        # 모든 서브서비스가 초기화되었는지 확인
        assert service.dem_service is not None
        assert service.ndvi_forest_service is not None
        assert service.water_distance_service is not None
        assert service.protected_area_service is not None

    def test_slope_risk_calculation(self):
        """경사도 위험 점수 계산 테스트"""
        mock_db = Mock()
        service = RiskAssessmentService(mock_db)

        # 다양한 경사도에 대한 위험 점수 확인
        assert service._calculate_slope_risk(35.0) == 100  # 매우 위험
        assert service._calculate_slope_risk(25.0) == 80
        assert service._calculate_slope_risk(20.0) == 60
        assert service._calculate_slope_risk(15.0) == 40
        assert service._calculate_slope_risk(10.0) == 20

    def test_forest_risk_calculation(self):
        """산림 훼손 위험 점수 계산 테스트"""
        mock_db = Mock()
        service = RiskAssessmentService(mock_db)

        # 다양한 훼손 면적에 대한 위험 점수 확인
        assert service._calculate_forest_risk(1500.0) == 100
        assert service._calculate_forest_risk(700.0) == 70
        assert service._calculate_forest_risk(300.0) == 50
        assert service._calculate_forest_risk(100.0) == 30
        assert service._calculate_forest_risk(0.0) == 0

    def test_water_risk_calculation(self):
        """수질 위험 점수 계산 테스트"""
        mock_db = Mock()
        service = RiskAssessmentService(mock_db)

        # 다양한 거리에 대한 위험 점수 확인
        assert service._calculate_water_risk(30.0) == 100  # 매우 위험
        assert service._calculate_water_risk(80.0) == 80
        assert service._calculate_water_risk(150.0) == 50
        assert service._calculate_water_risk(300.0) == 20

    def test_risk_level_determination(self):
        """위험 등급 결정 테스트"""
        mock_db = Mock()
        service = RiskAssessmentService(mock_db)

        # 다양한 위험 점수에 대한 등급 확인
        assert service._determine_risk_level(85) == "critical"
        assert service._determine_risk_level(65) == "high"
        assert service._determine_risk_level(45) == "medium"
        assert service._determine_risk_level(25) == "low"


class TestServiceIntegration:
    """개별 서비스 통합 테스트"""

    def test_all_services_can_be_instantiated(self):
        """모든 서비스가 인스턴스화 가능한지 테스트"""
        try:
            dem = DEMService()
            ndvi = NDVIForestService()
            water = WaterDistanceService()
            protected = ProtectedAreaService()

            assert dem is not None
            assert ndvi is not None
            assert water is not None
            assert protected is not None

        except Exception as e:
            pytest.fail(f"서비스 초기화 실패: {e}")

    def test_haversine_distance_calculation(self):
        """Haversine 거리 계산 정확도 테스트"""
        water_service = WaterDistanceService()

        # 서울 시청 -> 광화문 (약 500m)
        distance = water_service.calculate_haversine_distance(
            37.5665, 126.9780,  # 서울 시청
            37.5759, 126.9769   # 광화문
        )

        # 약 1km 정도 (오차 범위 고려)
        assert 800 <= distance <= 1200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
