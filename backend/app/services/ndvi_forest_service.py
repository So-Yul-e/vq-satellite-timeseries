"""
NDVI 및 산림 분석 서비스
위성 영상을 활용한 NDVI 계산 및 산림 변화 탐지
"""
import ee
from typing import Optional, Dict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class NDVIForestService:
    """NDVI 및 산림 분석 서비스"""

    def __init__(self):
        """서비스 초기화"""
        try:
            ee.Initialize()
        except Exception as e:
            logger.warning(f"Earth Engine 초기화 실패: {e}")

    def calculate_ndvi_at_location(
        self,
        latitude: float,
        longitude: float,
        date: Optional[datetime] = None,
        buffer_m: float = 100
    ) -> float:
        """
        특정 위치의 NDVI 계산

        Args:
            latitude: 위도
            longitude: 경도
            date: 분석 날짜 (None이면 최근 데이터 사용)
            buffer_m: 분석 반경 (미터)

        Returns:
            NDVI 값 (-1.0 ~ 1.0)
        """
        try:
            # 포인트 및 영역 생성
            point = ee.Geometry.Point([longitude, latitude])
            region = point.buffer(buffer_m)

            # 날짜 범위 설정
            if date is None:
                end_date = datetime.now()
            else:
                end_date = date

            start_date = end_date - timedelta(days=30)  # 최근 30일

            # Sentinel-2 영상 로드 (구름 필터링)
            s2_collection = (
                ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(region)
                .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
            )

            # 영상이 있는지 확인
            count = s2_collection.size().getInfo()
            if count == 0:
                logger.warning(f"해당 기간에 사용 가능한 Sentinel-2 영상이 없습니다")
                return 0.0

            # 중앙값 합성 (구름 제거)
            s2_median = s2_collection.median()

            # NDVI 계산: (NIR - Red) / (NIR + Red)
            # Sentinel-2: B8 = NIR, B4 = Red
            ndvi = s2_median.normalizedDifference(['B8', 'B4'])

            # 영역 내 평균 NDVI 계산
            ndvi_stats = ndvi.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=region,
                scale=10,  # 10m 해상도
                maxPixels=1e9
            )

            ndvi_value = ndvi_stats.get('nd').getInfo()

            if ndvi_value is None:
                logger.warning(f"NDVI 계산 실패: ({latitude}, {longitude})")
                return 0.0

            return float(ndvi_value)

        except Exception as e:
            logger.error(f"NDVI 계산 중 오류: {e}")
            return 0.0

    def detect_forest_change(
        self,
        latitude: float,
        longitude: float,
        before_date: datetime,
        after_date: datetime,
        buffer_m: float = 100
    ) -> Dict:
        """
        산림 변화 탐지 (NDVI 변화 분석)

        Args:
            latitude: 위도
            longitude: 경도
            before_date: 이전 날짜
            after_date: 이후 날짜
            buffer_m: 분석 반경

        Returns:
            변화 탐지 결과 딕셔너리
        """
        try:
            point = ee.Geometry.Point([longitude, latitude])
            region = point.buffer(buffer_m)

            # 이전 NDVI 계산
            before_ndvi = self._get_ndvi_for_period(
                region,
                before_date - timedelta(days=15),
                before_date + timedelta(days=15)
            )

            # 이후 NDVI 계산
            after_ndvi = self._get_ndvi_for_period(
                region,
                after_date - timedelta(days=15),
                after_date + timedelta(days=15)
            )

            # NDVI 변화량 계산
            ndvi_change = after_ndvi.subtract(before_ndvi)

            # 통계 계산
            stats = ndvi_change.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    reducer2=ee.Reducer.min(),
                    sharedInputs=True
                ).combine(
                    reducer2=ee.Reducer.max(),
                    sharedInputs=True
                ),
                geometry=region,
                scale=10,
                maxPixels=1e9
            )

            result = stats.getInfo()

            # 변화 분류
            mean_change = result.get('nd_mean', 0)
            is_deforestation = mean_change < -0.2  # NDVI가 크게 감소하면 산림 훼손

            # 훼손 면적 추정 (변화가 큰 픽셀 수)
            threshold_change = ndvi_change.lt(-0.2)
            damaged_area = threshold_change.multiply(ee.Image.pixelArea())
            total_damaged_area = damaged_area.reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=region,
                scale=10,
                maxPixels=1e9
            ).getInfo()

            return {
                "ndvi_change_mean": float(mean_change),
                "ndvi_change_min": float(result.get('nd_min', 0)),
                "ndvi_change_max": float(result.get('nd_max', 0)),
                "is_deforestation": bool(is_deforestation),
                "damaged_area_m2": float(total_damaged_area.get('nd', 0))
            }

        except Exception as e:
            logger.error(f"산림 변화 탐지 중 오류: {e}")
            return {
                "ndvi_change_mean": 0.0,
                "ndvi_change_min": 0.0,
                "ndvi_change_max": 0.0,
                "is_deforestation": False,
                "damaged_area_m2": 0.0
            }

    def _get_ndvi_for_period(
        self,
        region: ee.Geometry,
        start_date: datetime,
        end_date: datetime
    ) -> ee.Image:
        """
        기간 내 NDVI 중앙값 계산

        Args:
            region: 분석 영역
            start_date: 시작 날짜
            end_date: 종료 날짜

        Returns:
            NDVI 이미지
        """
        s2_collection = (
            ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(region)
            .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
        )

        s2_median = s2_collection.median()
        ndvi = s2_median.normalizedDifference(['B8', 'B4'])

        return ndvi

    def estimate_forest_damage_area(
        self,
        latitude: float,
        longitude: float,
        area_m2: float
    ) -> float:
        """
        산림 훼손 면적 추정

        Args:
            latitude: 위도
            longitude: 경도
            area_m2: 패널 면적 (m²)

        Returns:
            추정 산림 훼손 면적 (m²)
        """
        try:
            # 현재 NDVI 계산
            current_ndvi = self.calculate_ndvi_at_location(latitude, longitude, buffer_m=50)

            # NDVI 임계값 기반 산림 여부 판단
            # NDVI > 0.4: 울창한 숲
            # NDVI 0.2-0.4: 희박한 식생
            # NDVI < 0.2: 비식생 지역

            if current_ndvi < 0.2:
                # 현재 식생이 거의 없음 -> 산림 훼손 없음
                return 0.0
            elif current_ndvi < 0.4:
                # 희박한 식생 -> 패널 면적의 50% 정도 훼손 추정
                return area_m2 * 0.5
            else:
                # 울창한 숲 -> 패널 면적의 80% 정도 훼손 추정
                return area_m2 * 0.8

        except Exception as e:
            logger.error(f"산림 훼손 면적 추정 중 오류: {e}")
            # 안전하게 패널 면적을 반환 (최대 추정)
            return area_m2

    def get_forest_classification(
        self,
        latitude: float,
        longitude: float
    ) -> str:
        """
        산림 분류 (NDVI 기반)

        Args:
            latitude: 위도
            longitude: 경도

        Returns:
            산림 분류 ('dense_forest', 'sparse_forest', 'non_forest')
        """
        try:
            ndvi = self.calculate_ndvi_at_location(latitude, longitude)

            if ndvi > 0.4:
                return "dense_forest"
            elif ndvi > 0.2:
                return "sparse_forest"
            else:
                return "non_forest"

        except Exception as e:
            logger.error(f"산림 분류 중 오류: {e}")
            return "unknown"
