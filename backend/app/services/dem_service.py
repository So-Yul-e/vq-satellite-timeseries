"""
DEM (Digital Elevation Model) 서비스
경사도 및 표고 데이터 처리
"""
import ee
import numpy as np
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class DEMService:
    """DEM 데이터 처리 서비스"""

    def __init__(self):
        """서비스 초기화"""
        try:
            # Earth Engine 초기화 확인
            ee.Initialize()
        except Exception as e:
            logger.warning(f"Earth Engine 초기화 실패: {e}")

    def get_slope_at_location(
        self,
        latitude: float,
        longitude: float,
        buffer_m: float = 100
    ) -> float:
        """
        특정 위치의 경사도 계산

        Args:
            latitude: 위도
            longitude: 경도
            buffer_m: 분석 반경 (미터)

        Returns:
            경사도 (도 단위, 0-90)
        """
        try:
            # 포인트 생성
            point = ee.Geometry.Point([longitude, latitude])

            # 버퍼 영역 생성 (분석 범위)
            region = point.buffer(buffer_m)

            # SRTM DEM 데이터 로드 (90m 해상도)
            dem = ee.Image('USGS/SRTMGL1_003')

            # 경사도 계산 (도 단위)
            slope = ee.Terrain.slope(dem)

            # 해당 영역의 평균 경사도 계산
            slope_stats = slope.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=region,
                scale=30,  # 30m 해상도로 샘플링
                maxPixels=1e9
            )

            # 결과 추출
            slope_value = slope_stats.get('slope').getInfo()

            if slope_value is None:
                logger.warning(f"경사도 계산 실패: ({latitude}, {longitude})")
                return 0.0

            return float(slope_value)

        except Exception as e:
            logger.error(f"경사도 계산 중 오류: {e}")
            return 0.0

    def get_elevation_at_location(
        self,
        latitude: float,
        longitude: float
    ) -> float:
        """
        특정 위치의 표고 계산

        Args:
            latitude: 위도
            longitude: 경도

        Returns:
            표고 (미터)
        """
        try:
            # 포인트 생성
            point = ee.Geometry.Point([longitude, latitude])

            # SRTM DEM 데이터 로드
            dem = ee.Image('USGS/SRTMGL1_003')

            # 표고 추출
            elevation_stats = dem.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=point,
                scale=30
            )

            elevation_value = elevation_stats.get('elevation').getInfo()

            if elevation_value is None:
                logger.warning(f"표고 계산 실패: ({latitude}, {longitude})")
                return 0.0

            return float(elevation_value)

        except Exception as e:
            logger.error(f"표고 계산 중 오류: {e}")
            return 0.0

    def get_terrain_analysis(
        self,
        latitude: float,
        longitude: float,
        buffer_m: float = 100
    ) -> dict:
        """
        종합 지형 분석

        Args:
            latitude: 위도
            longitude: 경도
            buffer_m: 분석 반경 (미터)

        Returns:
            지형 분석 결과 딕셔너리
        """
        try:
            point = ee.Geometry.Point([longitude, latitude])
            region = point.buffer(buffer_m)

            # SRTM DEM 로드
            dem = ee.Image('USGS/SRTMGL1_003')

            # 경사도 계산
            slope = ee.Terrain.slope(dem)

            # 향(Aspect) 계산
            aspect = ee.Terrain.aspect(dem)

            # 통계 계산
            stats = dem.addBands(slope).addBands(aspect).reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    reducer2=ee.Reducer.max(),
                    sharedInputs=True
                ).combine(
                    reducer2=ee.Reducer.min(),
                    sharedInputs=True
                ),
                geometry=region,
                scale=30,
                maxPixels=1e9
            )

            result = stats.getInfo()

            return {
                "elevation_mean": result.get('elevation_mean', 0.0),
                "elevation_max": result.get('elevation_max', 0.0),
                "elevation_min": result.get('elevation_min', 0.0),
                "slope_mean": result.get('slope_mean', 0.0),
                "slope_max": result.get('slope_max', 0.0),
                "aspect_mean": result.get('aspect_mean', 0.0),
            }

        except Exception as e:
            logger.error(f"지형 분석 중 오류: {e}")
            return {
                "elevation_mean": 0.0,
                "elevation_max": 0.0,
                "elevation_min": 0.0,
                "slope_mean": 0.0,
                "slope_max": 0.0,
                "aspect_mean": 0.0,
            }

    def calculate_slope_from_dem_array(self, dem_array: np.ndarray, pixel_size: float = 30) -> np.ndarray:
        """
        DEM 배열로부터 직접 경사도 계산 (로컬 처리)

        Args:
            dem_array: DEM 고도 배열 (2D numpy array)
            pixel_size: 픽셀 크기 (미터)

        Returns:
            경사도 배열 (도 단위)
        """
        # Sobel 필터를 이용한 경사도 계산
        from scipy import ndimage

        # X, Y 방향 기울기 계산
        dx = ndimage.sobel(dem_array, axis=1) / (8 * pixel_size)
        dy = ndimage.sobel(dem_array, axis=0) / (8 * pixel_size)

        # 경사도 계산 (라디안)
        slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))

        # 도 단위로 변환
        slope_deg = np.degrees(slope_rad)

        return slope_deg
