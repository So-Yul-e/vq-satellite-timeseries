"""
보호 구역 검사 서비스
국립공원, 생태경관보전지역 등 보호구역과의 교차 분석
"""
import ee
from typing import Optional, Dict, List
from shapely.geometry import Point, shape
import logging

logger = logging.getLogger(__name__)


class ProtectedAreaService:
    """보호 구역 검사 서비스"""

    def __init__(self):
        """서비스 초기화"""
        try:
            ee.Initialize()
        except Exception as e:
            logger.warning(f"Earth Engine 초기화 실패: {e}")

        # 보호구역 데이터 (추후 실제 GeoJSON 파일 또는 DB로 대체)
        self.protected_areas = []

    def check_protected_area_violation(
        self,
        latitude: float,
        longitude: float,
        buffer_m: float = 50
    ) -> bool:
        """
        보호 구역 침범 여부 확인

        Args:
            latitude: 위도
            longitude: 경도
            buffer_m: 검사 반경 (미터)

        Returns:
            침범 여부 (True: 침범, False: 미침범)
        """
        try:
            # 포인트 생성
            point = ee.Geometry.Point([longitude, latitude])
            region = point.buffer(buffer_m)

            # WDPA (World Database on Protected Areas) 사용
            # Google Earth Engine의 보호구역 데이터셋
            wdpa = ee.FeatureCollection('WCMC/WDPA/current/polygons')

            # 해당 위치와 교차하는 보호구역 검색
            intersecting_areas = wdpa.filterBounds(region)

            # 교차하는 보호구역 개수 확인
            count = intersecting_areas.size().getInfo()

            if count > 0:
                logger.warning(f"보호 구역 침범 감지: {count}개 보호구역과 교차")
                return True

            return False

        except Exception as e:
            logger.error(f"보호 구역 검사 중 오류: {e}")
            # 오류 시 안전하게 False 반환 (보수적 판단)
            return False

    def get_protected_area_info(
        self,
        latitude: float,
        longitude: float,
        buffer_m: float = 100
    ) -> Dict:
        """
        주변 보호 구역 정보 조회

        Args:
            latitude: 위도
            longitude: 경도
            buffer_m: 검색 반경

        Returns:
            보호 구역 정보 딕셔너리
        """
        try:
            point = ee.Geometry.Point([longitude, latitude])
            region = point.buffer(buffer_m)

            # WDPA 보호구역 데이터
            wdpa = ee.FeatureCollection('WCMC/WDPA/current/polygons')

            # 교차하는 보호구역 검색
            intersecting_areas = wdpa.filterBounds(region)

            count = intersecting_areas.size().getInfo()

            if count == 0:
                return {
                    "is_protected": False,
                    "count": 0,
                    "areas": []
                }

            # 보호구역 정보 추출 (최대 5개)
            areas_list = intersecting_areas.limit(5).getInfo()

            protected_areas = []
            for feature in areas_list.get('features', []):
                props = feature.get('properties', {})
                protected_areas.append({
                    "name": props.get('NAME', 'Unknown'),
                    "type": props.get('DESIG_ENG', 'Unknown'),
                    "iucn_category": props.get('IUCN_CAT', 'Unknown'),
                    "status": props.get('STATUS', 'Unknown')
                })

            return {
                "is_protected": True,
                "count": count,
                "areas": protected_areas
            }

        except Exception as e:
            logger.error(f"보호 구역 정보 조회 중 오류: {e}")
            return {
                "is_protected": False,
                "count": 0,
                "areas": []
            }

    def check_korea_protected_areas(
        self,
        latitude: float,
        longitude: float
    ) -> Dict:
        """
        한국 보호 구역 검사 (국내 특화)

        한국의 주요 보호 구역:
        - 국립공원
        - 도립공원
        - 생태경관보전지역
        - 야생동물보호구역
        - 습지보호구역

        Args:
            latitude: 위도
            longitude: 경도

        Returns:
            보호 구역 검사 결과
        """
        # 한국 보호구역 좌표 범위 확인 (대략적인 범위)
        if not (33.0 <= latitude <= 38.6 and 124.5 <= longitude <= 131.9):
            logger.info("한국 범위 밖의 좌표입니다")
            return {
                "is_korea_protected": False,
                "protected_type": None
            }

        # WDPA에서 한국 보호구역 검색
        try:
            point = ee.Geometry.Point([longitude, latitude])

            # 한국 보호구역 필터링 (ISO3 코드 'KOR')
            korea_protected = ee.FeatureCollection('WCMC/WDPA/current/polygons').filter(
                ee.Filter.eq('ISO3', 'KOR')
            )

            # 해당 위치와 교차 확인
            intersecting = korea_protected.filterBounds(point)
            count = intersecting.size().getInfo()

            if count > 0:
                # 첫 번째 보호구역 정보 추출
                first_area = intersecting.first().getInfo()
                props = first_area.get('properties', {})

                return {
                    "is_korea_protected": True,
                    "protected_type": props.get('DESIG_ENG', 'Unknown'),
                    "name": props.get('NAME', 'Unknown'),
                    "iucn_category": props.get('IUCN_CAT', 'Unknown')
                }

            return {
                "is_korea_protected": False,
                "protected_type": None
            }

        except Exception as e:
            logger.error(f"한국 보호구역 검사 중 오류: {e}")
            return {
                "is_korea_protected": False,
                "protected_type": None
            }

    def check_multiple_protections(
        self,
        latitude: float,
        longitude: float
    ) -> List[str]:
        """
        다중 보호 지정 확인

        한 지역이 여러 보호 구역에 중복 지정된 경우 확인

        Args:
            latitude: 위도
            longitude: 경도

        Returns:
            보호 구역 유형 리스트
        """
        try:
            info = self.get_protected_area_info(latitude, longitude, buffer_m=10)

            if not info['is_protected']:
                return []

            protection_types = []
            for area in info['areas']:
                area_type = area.get('type', 'Unknown')
                if area_type not in protection_types:
                    protection_types.append(area_type)

            return protection_types

        except Exception as e:
            logger.error(f"다중 보호 지정 확인 중 오류: {e}")
            return []

    def get_protection_severity(
        self,
        latitude: float,
        longitude: float
    ) -> int:
        """
        보호 구역 위반 심각도 계산

        Args:
            latitude: 위도
            longitude: 경도

        Returns:
            심각도 점수 (0-100)
        """
        try:
            info = self.get_protected_area_info(latitude, longitude, buffer_m=50)

            if not info['is_protected']:
                return 0

            # IUCN 카테고리별 심각도
            # Ia, Ib: Strict Nature Reserve (100점)
            # II: National Park (90점)
            # III: Natural Monument (80점)
            # IV: Habitat/Species Management Area (70점)
            # V: Protected Landscape (60점)
            # VI: Protected area with sustainable use (50점)

            max_severity = 0

            for area in info['areas']:
                iucn_cat = area.get('iucn_category', '')

                if iucn_cat in ['Ia', 'Ib']:
                    severity = 100
                elif iucn_cat == 'II':
                    severity = 90
                elif iucn_cat == 'III':
                    severity = 80
                elif iucn_cat == 'IV':
                    severity = 70
                elif iucn_cat == 'V':
                    severity = 60
                elif iucn_cat == 'VI':
                    severity = 50
                else:
                    severity = 40  # 기타 보호구역

                max_severity = max(max_severity, severity)

            # 다중 보호 지정 시 가중치 추가
            if info['count'] > 1:
                max_severity = min(100, max_severity + 10)

            return max_severity

        except Exception as e:
            logger.error(f"보호 심각도 계산 중 오류: {e}")
            return 0
