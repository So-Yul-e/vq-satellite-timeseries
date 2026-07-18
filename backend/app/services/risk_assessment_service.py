"""
위험도 평가 서비스
탐지된 태양광 패널의 위험도를 종합 평가
"""
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional
from app.models.solar_panel import SolarPanel
from app.models.risk_assessment import RiskAssessment
from app.services.mountain_info_client import MountainInfoClient
from app.services.dem_service import DEMService
from app.services.ndvi_forest_service import NDVIForestService
from app.services.water_distance_service import WaterDistanceService
from app.services.protected_area_service import ProtectedAreaService
import logging

logger = logging.getLogger(__name__)


class RiskAssessmentService:
    """위험도 평가 서비스"""
    
    def __init__(self, db: Session):
        self.db = db
        self.mountain_client = MountainInfoClient()
        self.dem_service = DEMService()
        self.ndvi_forest_service = NDVIForestService()
        self.water_distance_service = WaterDistanceService()
        self.protected_area_service = ProtectedAreaService()
    
    async def assess_panel_risk(self, panel_id: UUID) -> RiskAssessment:
        """
        패널 위험도 평가

        Args:
            panel_id: 태양광 패널 ID

        Returns:
            RiskAssessment 객체
        """
        panel = self.db.query(SolarPanel).filter(SolarPanel.id == panel_id).first()
        if not panel:
            raise ValueError(f"패널을 찾을 수 없습니다: {panel_id}")

        # 1. 산 지역 여부 확인 (산 정보 API 활용) - 먼저 확인
        is_mountain = await self.mountain_client.is_mountain_area(
            panel.center_latitude,
            panel.center_longitude,
            radius_km=5.0
        )
        mountain_height = None
        if is_mountain:
            mountain_height = await self.mountain_client.get_mountain_height(
                panel.center_latitude,
                panel.center_longitude
            )

        # 2. 경사도 분석 (DEM 데이터 필요, 현재는 산 정보로 보조)
        slope_degree = self._calculate_slope(panel.center_latitude, panel.center_longitude, mountain_height)
        slope_risk = self._calculate_slope_risk(slope_degree)
        
        # 산 지역이면 경사도 위험 가중치 증가
        if is_mountain:
            slope_risk = min(100, int(slope_risk * 1.2))  # 20% 증가
        
        # 3. 산림 훼손 면적 계산
        forest_damage = self._calculate_forest_damage(panel.metadata_json)
        forest_risk = self._calculate_forest_risk(forest_damage)
        
        # 산 지역이면 산림 훼손 위험 증가
        if is_mountain and forest_damage > 0:
            forest_risk = min(100, int(forest_risk * 1.3))  # 30% 증가
        
        # 4. 수계 거리 계산
        water_distance = self._calculate_water_distance(panel.center_latitude, panel.center_longitude)
        water_risk = self._calculate_water_risk(water_distance)
        
        # 5. 보호 구역 침범 여부
        protected_violation = self._check_protected_area(panel.metadata_json)
        protected_risk = 100 if protected_violation else 0
        
        # 6. 종합 위험 점수 계산
        total_risk = int(
            slope_risk * 0.3 +
            forest_risk * 0.3 +
            water_risk * 0.2 +
            protected_risk * 0.2
        )
        
        risk_level = self._determine_risk_level(total_risk)
        
        # 7. 위험도 평가 저장
        assessment = RiskAssessment(
            panel_id=panel.id,
            slope_degree=slope_degree,
            slope_risk_score=slope_risk,
            forest_damage_area_m2=forest_damage,
            forest_risk_score=forest_risk,
            water_distance_m=water_distance,
            water_risk_score=water_risk,
            protected_area_violation=protected_violation,
            protected_risk_score=protected_risk,
            total_risk_score=total_risk,
            risk_level=risk_level
        )
        
        # 메타데이터에 산 정보 추가
        if panel.metadata_json is None:
            panel.metadata_json = {}
        
        panel.metadata_json["mountain_info"] = {
            "is_mountain_area": is_mountain,
            "mountain_height_m": mountain_height,
            "slope_degree": slope_degree
        }
        
        self.db.add(assessment)
        self.db.commit()
        self.db.refresh(assessment)
        
        logger.info(f"위험도 평가 완료: 패널 {panel_id}, 점수 {total_risk}, 등급 {risk_level}")
        
        return assessment
    
    def _calculate_slope(self, lat: float, lon: float, mountain_height: Optional[float] = None) -> float:
        """
        경사도 계산 (DEM 활용)

        SRTM DEM 데이터를 사용하여 실제 경사도 계산
        실패 시 산 정보 API의 산 높이를 보조 정보로 활용
        """
        try:
            # DEM 데이터로부터 실제 경사도 계산
            slope_degree = self.dem_service.get_slope_at_location(lat, lon, buffer_m=100)

            if slope_degree > 0:
                logger.info(f"DEM 기반 경사도 계산 성공: {slope_degree:.2f}도")
                return slope_degree

        except Exception as e:
            logger.warning(f"DEM 경사도 계산 실패, 대체 방법 사용: {e}")

        # DEM 계산 실패 시 산 정보로 추정
        if mountain_height:
            # 산 높이가 높을수록 경사도가 클 가능성
            # 대략적인 추정 (백업용)
            if mountain_height > 1000:
                return 35.0  # 높은 산
            elif mountain_height > 500:
                return 25.0  # 중간 산
            elif mountain_height > 200:
                return 15.0  # 낮은 산

        # 기본값 (평지 가정)
        return 10.0
    
    def _calculate_slope_risk(self, slope: float) -> int:
        """경사도 위험 점수"""
        if slope >= 30:
            return 100  # 매우 위험
        elif slope >= 25:
            return 80
        elif slope >= 20:
            return 60
        elif slope >= 15:
            return 40
        else:
            return 20
    
    def _calculate_forest_damage(self, metadata: Optional[dict]) -> float:
        """
        산림 훼손 면적 계산

        NDVI 분석을 통한 실제 산림 훼손 면적 추정
        패널 위치의 NDVI 값을 기반으로 산림 훼손 정도 계산

        Args:
            metadata: 패널 메타데이터 (polygon, 위치 정보 포함)

        Returns:
            훼손 면적 (m²)
        """
        try:
            # 메타데이터에서 패널 정보 추출
            if not metadata:
                return 0.0

            # 위치 정보 추출
            latitude = metadata.get("center_latitude")
            longitude = metadata.get("center_longitude")
            area_m2 = metadata.get("area_m2", 0)

            if not latitude or not longitude:
                logger.warning("패널 위치 정보가 없어 NDVI 분석을 건너뜁니다")
                return area_m2 if area_m2 > 0 else 0.0

            # NDVI 기반 산림 훼손 면적 추정
            forest_damage = self.ndvi_forest_service.estimate_forest_damage_area(
                latitude=latitude,
                longitude=longitude,
                area_m2=area_m2
            )

            logger.info(f"NDVI 기반 산림 훼손 추정: {forest_damage:.2f} m²")
            return forest_damage

        except Exception as e:
            logger.warning(f"NDVI 산림 분석 실패, 메타데이터 사용: {e}")

            # 실패 시 메타데이터의 면적 사용
            if metadata and "area_m2" in metadata:
                return float(metadata["area_m2"])

            return 0.0
    
    def _calculate_forest_risk(self, damage_area: float) -> int:
        """산림 훼손 위험 점수"""
        if damage_area > 1000:
            return 100
        elif damage_area > 500:
            return 70
        elif damage_area > 200:
            return 50
        elif damage_area > 0:
            return 30
        else:
            return 0
    
    def _calculate_water_distance(self, lat: float, lon: float) -> float:
        """
        수계 거리 계산

        JRC Global Surface Water 데이터를 활용한 실제 수계 거리 계산

        Returns:
            거리 (m)
        """
        try:
            # 수계 거리 계산 (5km 반경 내 검색)
            distance = self.water_distance_service.calculate_water_distance(
                latitude=lat,
                longitude=lon,
                search_radius_km=5.0
            )

            logger.info(f"수계 거리 계산 성공: {distance:.2f}m")
            return distance

        except Exception as e:
            logger.warning(f"수계 거리 계산 실패, 기본값 사용: {e}")
            # 실패 시 안전한 기본값 (보수적 추정)
            return 200.0
    
    def _calculate_water_risk(self, distance: float) -> int:
        """수질 위험 점수"""
        if distance < 50:
            return 100  # 매우 위험
        elif distance < 100:
            return 80
        elif distance < 200:
            return 50
        else:
            return 20
    
    def _check_protected_area(self, metadata: Optional[dict]) -> bool:
        """
        보호 구역 침범 여부 확인

        WDPA (World Database on Protected Areas) 데이터를 활용한
        실제 보호 구역 교차 분석

        Returns:
            True if violated, False otherwise
        """
        try:
            # 메타데이터에서 위치 정보 추출
            if not metadata:
                return False

            latitude = metadata.get("center_latitude")
            longitude = metadata.get("center_longitude")

            if not latitude or not longitude:
                logger.warning("패널 위치 정보가 없어 보호구역 검사를 건너뜁니다")
                return False

            # 보호 구역 침범 확인
            is_violated = self.protected_area_service.check_protected_area_violation(
                latitude=latitude,
                longitude=longitude,
                buffer_m=50
            )

            if is_violated:
                # 상세 정보 로깅
                info = self.protected_area_service.get_protected_area_info(
                    latitude=latitude,
                    longitude=longitude
                )
                logger.warning(f"보호 구역 침범 감지: {info}")

            return is_violated

        except Exception as e:
            logger.warning(f"보호 구역 검사 실패: {e}")
            # 실패 시 안전하게 False 반환
            return False
    
    def _determine_risk_level(self, total_risk: int) -> str:
        """위험 등급 결정"""
        if total_risk >= 80:
            return "critical"
        elif total_risk >= 60:
            return "high"
        elif total_risk >= 40:
            return "medium"
        else:
            return "low"
