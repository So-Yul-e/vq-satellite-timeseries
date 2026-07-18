"""
태양광 패널 탐지 결과와 허가 데이터 매칭 서비스

패널-허가 근접 매칭은 PostGIS(ST_DWithin/ST_Distance, geography 캐스팅)로 수행한다.
(VERSION.md 2026-07-11 확정 결정 — PostGIS 즉시 도입)
"""
import logging
from sqlalchemy import cast, func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from geoalchemy2 import Geography, Geometry
from geoalchemy2.elements import WKTElement
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
import uuid

from app.models.solar_panel import SolarPanel
from app.models.solar_permit import SolarPermit
from app.models.panel_permit_match import PanelPermitMatch

logger = logging.getLogger(__name__)


class PanelPermitMatchingService:
    """태양광 패널 탐지 결과와 허가 데이터 매칭 서비스"""

    # 매칭 기준
    EXACT_MATCH_DISTANCE_M = 100  # 100m 이내는 정확 매칭
    NEARBY_MATCH_DISTANCE_M = 500  # 500m 이내는 근처 매칭
    SEARCH_RADIUS_KM = 2.0  # 2km 반경 내에서 검색

    # 면적 비율 기준 (태양광 패널 1kW ≈ 6-8m²)
    KW_TO_M2_RATIO = 7.0  # 평균 7m²/kW

    def __init__(self, db: Session):
        self.db = db

    def find_nearby_permits(
        self,
        panel: SolarPanel,
        radius_km: float = None
    ) -> List[Tuple[SolarPermit, float]]:
        """
        패널 주변의 허가 발전소 검색 (PostGIS ST_DWithin/ST_Distance)

        Args:
            panel: 태양광 패널 탐지 결과
            radius_km: 검색 반경 (km)

        Returns:
            [(permit, distance_m), ...] 리스트 (거리순 정렬)
        """
        if radius_km is None:
            radius_km = self.SEARCH_RADIUS_KM

        return self._find_nearby_permits_by_geom(panel.geom, radius_km)

    def match_coordinates_with_permits(
        self,
        latitude: float,
        longitude: float,
        area_m2: float = 0.0,
        radius_m: float = 100.0
    ) -> Dict:
        """
        아직 DB row가 없는 좌표(예: GEE 탐지 직후 임시 좌표)에 대해 허가 매칭 수행

        /api/solar/analyze처럼 SolarPanel row가 존재하지 않는 상황에서 사용한다.
        SolarPanel row를 즉석에서 생성하지 않고 좌표/면적만으로 매칭한다.

        Args:
            latitude: 위도
            longitude: 경도
            area_m2: 탐지 면적 (m²)
            radius_m: 검색 반경 (미터)

        Returns:
            매칭 결과 딕셔너리 (has_permit, is_legal 등)
        """
        point = WKTElement(f"POINT({longitude} {latitude})", srid=4326)
        radius_km = radius_m / 1000.0
        nearby_permits = self._find_nearby_permits_by_geom(point, radius_km)

        if not nearby_permits:
            return {
                "has_permit": False,
                "is_legal": False,
                "match_type": "suspected_illegal",
                "match_confidence": 0.9,
                "nearest_permit_distance_m": None,
                "matched_permits": [],
                "reason": f"주변 {radius_m:.0f}m 이내에 허가된 발전소가 없음"
            }

        nearest_permit, nearest_distance = nearby_permits[0]

        if nearest_distance <= self.EXACT_MATCH_DISTANCE_M:
            match_type = "exact"
            is_legal = True
            reason = f"허가된 발전소({nearest_permit.facility_name})로부터 {nearest_distance:.0f}m"
        elif nearest_distance <= self.NEARBY_MATCH_DISTANCE_M:
            match_type = "nearby"
            is_legal = True
            reason = f"허가된 발전소({nearest_permit.facility_name}) 근처 ({nearest_distance:.0f}m)"
        else:
            match_type = "suspected_illegal"
            is_legal = False
            reason = f"가장 가까운 허가 발전소로부터 {nearest_distance:.0f}m 떨어져 있음"

        return {
            "has_permit": is_legal,
            "is_legal": is_legal,
            "match_type": match_type,
            "nearest_permit_id": str(nearest_permit.id),
            "nearest_permit_name": nearest_permit.facility_name,
            "nearest_permit_distance_m": round(nearest_distance, 2),
            "matched_permits": [
                {
                    "permit_id": str(permit.id),
                    "permit_name": permit.facility_name,
                    "distance_m": round(dist, 2),
                    "capacity_kw": float(permit.capacity) if permit.capacity else None
                }
                for permit, dist in nearby_permits[:5]
            ],
            "reason": reason
        }

    def _find_nearby_permits_by_geom(
        self,
        geom,
        radius_km: float
    ) -> List[Tuple[SolarPermit, float]]:
        """
        geom 기준 ST_DWithin 근접 검색 공통 로직

        geom/SolarPermit.geom을 geography로 캐스팅해 미터 단위 정확도를 확보한다.
        geom은 ORM에서 로드된 WKBElement(예: panel.geom)일 수도, WKTElement일 수도
        있으므로 항상 Geometry로 먼저 캐스팅한 뒤 Geography로 재캐스팅한다
        (WKBElement를 Geography로 직접 캐스팅하면 ST_GeogFromText가 EWKB를 WKT로
        오인해 파싱 오류가 발생하는 GeoAlchemy2 이슈 회피).
        """
        if geom is None:
            return []

        radius_m = radius_km * 1000
        permit_geog = cast(SolarPermit.geom, Geography)
        target_geog = cast(cast(geom, Geometry), Geography)
        distance_col = func.ST_Distance(permit_geog, target_geog).label("distance_m")

        results_query = (
            self.db.query(SolarPermit, distance_col)
            .filter(SolarPermit.geom.isnot(None))
            .filter(func.ST_DWithin(permit_geog, target_geog, radius_m))
            .order_by(distance_col)
        )

        return [(permit, float(distance_m)) for permit, distance_m in results_query.all()]

    def calculate_area_ratio(
        self,
        panel_area_m2: float,
        permit_capacity_kw: Optional[Decimal]
    ) -> Optional[float]:
        """
        탐지된 면적과 허가 용량 비교

        Args:
            panel_area_m2: 탐지된 패널 면적 (m²)
            permit_capacity_kw: 허가 용량 (kW)

        Returns:
            면적 비율 (탐지 면적 / 예상 허가 면적)
        """
        if not permit_capacity_kw or permit_capacity_kw <= 0:
            return None

        expected_area_m2 = float(permit_capacity_kw) * self.KW_TO_M2_RATIO
        return float(panel_area_m2) / expected_area_m2

    def match_panel_with_permits(
        self,
        panel: SolarPanel,
        radius_km: float = None
    ) -> Dict:
        """
        단일 패널과 허가 데이터 매칭

        Args:
            panel: 태양광 패널 탐지 결과
            radius_km: 검색 반경 (km, 기본 SEARCH_RADIUS_KM)

        Returns:
            매칭 결과 딕셔너리
        """
        # 주변 허가 발전소 검색
        nearby_permits = self.find_nearby_permits(panel, radius_km=radius_km)

        if not nearby_permits:
            search_radius = radius_km if radius_km is not None else self.SEARCH_RADIUS_KM
            return {
                "panel_id": str(panel.id),
                "match_type": "suspected_illegal",
                "match_confidence": 0.9,
                "nearest_permit_distance_m": None,
                "matched_permits": [],
                "is_illegal": True,
                "reason": f"주변 {search_radius}km 이내에 허가된 발전소가 없음"
            }

        # 가장 가까운 허가 발전소
        nearest_permit, nearest_distance = nearby_permits[0]

        # 매칭 유형 결정
        if nearest_distance <= self.EXACT_MATCH_DISTANCE_M:
            match_type = "exact"
            match_confidence = 0.95
            is_illegal = False
            reason = f"허가된 발전소({nearest_permit.facility_name})로부터 {nearest_distance:.0f}m"

        elif nearest_distance <= self.NEARBY_MATCH_DISTANCE_M:
            match_type = "nearby"
            match_confidence = 0.7
            is_illegal = False
            reason = f"허가된 발전소({nearest_permit.facility_name}) 근처 ({nearest_distance:.0f}m)"

        else:
            match_type = "suspected_illegal"
            match_confidence = 0.8
            is_illegal = True
            reason = f"가장 가까운 허가 발전소로부터 {nearest_distance:.0f}m 떨어져 있음"

        # 면적 비교
        area_ratio = self.calculate_area_ratio(
            panel.area_m2,
            nearest_permit.capacity
        )

        return {
            "panel_id": str(panel.id),
            "match_type": match_type,
            "match_confidence": match_confidence,
            "nearest_permit_id": str(nearest_permit.id),
            "nearest_permit_name": nearest_permit.facility_name,
            "nearest_permit_distance_m": round(nearest_distance, 2),
            "area_ratio": round(area_ratio, 2) if area_ratio else None,
            "matched_permits": [
                {
                    "permit_id": str(permit.id),
                    "permit_name": permit.facility_name,
                    "distance_m": round(dist, 2),
                    "capacity_kw": float(permit.capacity) if permit.capacity else None
                }
                for permit, dist in nearby_permits[:5]  # 상위 5개
            ],
            "is_illegal": is_illegal,
            "reason": reason
        }

    def save_match_result(
        self,
        panel_id: uuid.UUID,
        permit_id: uuid.UUID,
        distance_m: float,
        match_type: str,
        match_confidence: float,
        area_ratio: Optional[float] = None
    ):
        """
        매칭 결과를 DB에 저장

        Args:
            panel_id: 패널 ID
            permit_id: 허가 ID
            distance_m: 거리 (m)
            match_type: 매칭 유형
            match_confidence: 매칭 신뢰도
            area_ratio: 면적 비율
        """
        stmt = pg_insert(PanelPermitMatch).values(
            panel_id=panel_id,
            permit_id=permit_id,
            distance_m=distance_m,
            match_type=match_type,
            match_confidence=match_confidence,
            area_ratio=area_ratio,
            status="pending",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["panel_id", "permit_id"],
            set_={
                "distance_m": stmt.excluded.distance_m,
                "match_type": stmt.excluded.match_type,
                "match_confidence": stmt.excluded.match_confidence,
                "area_ratio": stmt.excluded.area_ratio,
                "matched_at": func.current_timestamp(),
            },
        )

        self.db.execute(stmt)
        self.db.commit()

    def batch_match_panels(
        self,
        limit: int = 100,
        skip: int = 0,
        radius_km: float = None
    ) -> Dict:
        """
        여러 패널에 대해 일괄 매칭 수행

        Args:
            limit: 처리할 패널 수
            skip: 건너뛸 패널 수
            radius_km: 검색 반경 (km, 기본 SEARCH_RADIUS_KM)

        Returns:
            매칭 결과 통계
        """
        # 미매칭 패널 조회
        panels = self.db.query(SolarPanel).offset(skip).limit(limit).all()

        logger.info(f"배치 매칭 시작: {len(panels)}개 패널")

        matched_count = 0
        illegal_count = 0
        legal_count = 0

        for panel in panels:
            try:
                match_result = self.match_panel_with_permits(panel, radius_km=radius_km)

                # 매칭 결과 저장
                if match_result.get("nearest_permit_id"):
                    self.save_match_result(
                        panel_id=uuid.UUID(match_result["panel_id"]),
                        permit_id=uuid.UUID(match_result["nearest_permit_id"]),
                        distance_m=match_result["nearest_permit_distance_m"],
                        match_type=match_result["match_type"],
                        match_confidence=match_result["match_confidence"],
                        area_ratio=match_result.get("area_ratio")
                    )
                    matched_count += 1

                # 패널 상태 업데이트
                panel.is_legal = not match_result["is_illegal"]
                if match_result["is_illegal"]:
                    panel.status = "illegal_confirmed"
                    illegal_count += 1
                else:
                    panel.status = "legal_confirmed"
                    legal_count += 1

                self.db.commit()

            except Exception as e:
                logger.error(f"패널 {panel.id} 매칭 실패: {e}")
                self.db.rollback()
                continue

        logger.info(f"배치 매칭 완료: 매칭={matched_count}, 불법={illegal_count}, 합법={legal_count}")

        return {
            "total_processed": len(panels),
            "matched": matched_count,
            "illegal": illegal_count,
            "legal": legal_count
        }

    def get_permit_statistics(self) -> Dict:
        """전국 허가(SolarPermit) 데이터 통계"""
        try:
            total_permits = self.db.query(SolarPermit).count()
            permits_with_coords = self.db.query(SolarPermit).filter(
                SolarPermit.geom.isnot(None)
            ).count()

            return {
                "total_permits": total_permits,
                "permits_with_coordinates": permits_with_coords,
                "coverage_percent": round(
                    (permits_with_coords / total_permits * 100) if total_permits > 0 else 0, 1
                )
            }

        except Exception as e:
            logger.error(f"허가 통계 조회 오류: {e}")
            return {
                "total_permits": 0,
                "permits_with_coordinates": 0,
                "coverage_percent": 0
            }
