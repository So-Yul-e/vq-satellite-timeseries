"""
수계 거리 계산 서비스
하천, 호수 등 수계와의 거리 계산
"""
import ee
from typing import Optional, Dict, Tuple
import logging
import math

logger = logging.getLogger(__name__)


class WaterDistanceService:
    """수계 거리 계산 서비스"""

    def __init__(self):
        """서비스 초기화"""
        try:
            ee.Initialize()
        except Exception as e:
            logger.warning(f"Earth Engine 초기화 실패: {e}")

    def calculate_water_distance(
        self,
        latitude: float,
        longitude: float,
        search_radius_km: float = 5.0
    ) -> float:
        """
        최인접 수계까지의 거리 계산

        Args:
            latitude: 위도
            longitude: 경도
            search_radius_km: 검색 반경 (km)

        Returns:
            최단 거리 (미터)
        """
        try:
            # 포인트 생성
            point = ee.Geometry.Point([longitude, latitude])

            # 검색 영역 생성
            search_radius_m = search_radius_km * 1000
            search_region = point.buffer(search_radius_m)

            # JRC Global Surface Water 데이터 사용
            # 1984년부터 현재까지의 지표수 발생 빈도
            water_occurrence = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence')

            # 수계 마스크 생성 (발생 빈도 > 50%인 지역을 영구 수계로 간주)
            water_mask = water_occurrence.gt(50)

            # 검색 영역 내 수계 추출
            water_in_region = water_mask.updateMask(water_mask).clip(search_region)

            # 수계까지의 거리 계산 (거리 변환)
            distance_image = water_in_region.fastDistanceTransform().sqrt().multiply(ee.Image.pixelArea().sqrt())

            # 포인트에서의 거리 추출
            distance_stats = distance_image.reduceRegion(
                reducer=ee.Reducer.min(),
                geometry=point.buffer(10),  # 포인트 주변 작은 영역
                scale=30,
                maxPixels=1e9
            )

            distance_value = distance_stats.get('occurrence').getInfo()

            if distance_value is None or distance_value > search_radius_m:
                # 검색 반경 내에 수계가 없음
                logger.info(f"검색 반경 {search_radius_km}km 내에 수계가 없습니다")
                return search_radius_m

            return float(distance_value)

        except Exception as e:
            logger.error(f"수계 거리 계산 중 오류: {e}")
            # 오류 시 안전하게 큰 값 반환 (보수적 추정)
            return search_radius_km * 1000

    def get_water_body_info(
        self,
        latitude: float,
        longitude: float,
        buffer_m: float = 100
    ) -> Dict:
        """
        주변 수계 정보 조회

        Args:
            latitude: 위도
            longitude: 경도
            buffer_m: 분석 반경 (미터)

        Returns:
            수계 정보 딕셔너리
        """
        try:
            point = ee.Geometry.Point([longitude, latitude])
            region = point.buffer(buffer_m)

            # JRC Global Surface Water 데이터
            gsw = ee.Image('JRC/GSW1_4/GlobalSurfaceWater')

            # 여러 지표 추출
            occurrence = gsw.select('occurrence')  # 발생 빈도
            change_abs = gsw.select('change_abs')  # 절대 변화량
            seasonality = gsw.select('seasonality')  # 계절성
            max_extent = gsw.select('max_extent')  # 최대 범위

            # 통계 계산
            stats = gsw.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=region,
                scale=30,
                maxPixels=1e9
            )

            result = stats.getInfo()

            occurrence_value = result.get('occurrence', 0)
            is_water_body = occurrence_value > 50

            # 수계 유형 분류
            water_type = self._classify_water_type(
                occurrence_value,
                result.get('seasonality', 0)
            )

            return {
                "is_near_water": is_water_body,
                "water_occurrence": float(occurrence_value),
                "water_type": water_type,
                "seasonality": float(result.get('seasonality', 0)),
                "max_extent": float(result.get('max_extent', 0))
            }

        except Exception as e:
            logger.error(f"수계 정보 조회 중 오류: {e}")
            return {
                "is_near_water": False,
                "water_occurrence": 0.0,
                "water_type": "unknown",
                "seasonality": 0.0,
                "max_extent": 0.0
            }

    def _classify_water_type(self, occurrence: float, seasonality: float) -> str:
        """
        수계 유형 분류

        Args:
            occurrence: 수계 발생 빈도 (%)
            seasonality: 계절성 (개월 수)

        Returns:
            수계 유형
        """
        if occurrence < 10:
            return "non_water"
        elif occurrence >= 90:
            if seasonality >= 11:
                return "permanent_water"  # 영구 수계
            else:
                return "seasonal_water"  # 계절성 수계
        elif occurrence >= 50:
            return "frequent_water"  # 빈번한 수계
        else:
            return "occasional_water"  # 가끔 있는 수계

    def check_water_proximity_risk(
        self,
        latitude: float,
        longitude: float,
        risk_threshold_m: float = 200
    ) -> Tuple[bool, float]:
        """
        수계 근접 위험 확인

        Args:
            latitude: 위도
            longitude: 경도
            risk_threshold_m: 위험 임계 거리 (미터)

        Returns:
            (위험 여부, 거리)
        """
        distance = self.calculate_water_distance(latitude, longitude)

        is_risky = distance < risk_threshold_m

        return is_risky, distance

    def calculate_haversine_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """
        두 지점 간의 Haversine 거리 계산

        Args:
            lat1, lon1: 첫 번째 지점 (위도, 경도)
            lat2, lon2: 두 번째 지점 (위도, 경도)

        Returns:
            거리 (미터)
        """
        # 지구 반경 (미터)
        R = 6371000

        # 라디안 변환
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        # Haversine 공식
        a = (
            math.sin(delta_lat / 2) ** 2 +
            math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        distance = R * c

        return distance
