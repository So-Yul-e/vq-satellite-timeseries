"""
산지 판정 클라이언트 — VWorld(브이월드) 산림입지도(Data API, lt_c_fsdifrsts) 기반

기존에는 산림청 산 정보 API(mntInfoOpenAPI2, 산 "이름" 검색용)로 좌표 판정을 시도했으나,
그 API는 좌표 파라미터도 산 좌표 필드도 제공하지 않아 구조적으로 산지 판정이 불가능했다
(설악산 좌표를 넣어도 항상 False). VWorld 산림입지도는 실제 폴리곤 기반 공간 조회라
좌표 포인트가 산림입지 폴리곤 안에 있는지를 정확히 판정한다.
검증(2026-07-12): 설악산(38.1197,128.4655)→OK, 무안 평야(34.83,126.40)→NOT_FOUND.
"""
import httpx
import logging
from typing import Dict, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

_VWORLD_DATA_URL = "https://api.vworld.kr/req/data"
_FOREST_SITE_LAYER = "lt_c_fsdifrsts"  # 산림입지도


class MountainInfoClient:
    """VWorld 산림입지도 기반 산지 판정 클라이언트"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.VWORLD_API_KEY
        self.domain = settings.VWORLD_REQUEST_DOMAIN

    async def get_mountain_info(self, latitude: float, longitude: float, radius_km: float = 5.0) -> Optional[Dict]:
        """
        좌표가 산림입지 폴리곤 안에 있는지 조회한다.

        Args:
            latitude: 위도
            longitude: 경도
            radius_km: 미사용(포인트 폴리곤 포함 여부만 판정 — 반경 검색 아님).
                기존 호출부와의 시그니처 호환을 위해 남겨둔다.

        Returns:
            산림입지 속성 딕셔너리(예: {"name": "제지", "toyanghyun": "R"}) 또는 None
        """
        if not self.api_key:
            logger.warning("VWORLD_API_KEY가 설정되지 않아 산지 판정을 건너뜁니다")
            return None

        try:
            params = {
                "service": "data",
                "request": "GetFeature",
                "key": self.api_key,
                "domain": self.domain,
                "data": _FOREST_SITE_LAYER,
                "geomFilter": f"POINT({longitude} {latitude})",
                "size": "1",
                "format": "json",
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(_VWORLD_DATA_URL, params=params, timeout=10.0)
                response.raise_for_status()

            data = response.json()
            resp = data.get("response", {})
            if resp.get("status") != "OK":
                # NOT_FOUND(산지 아님)를 포함해 정상적인 "없음" 응답
                return None

            features = resp.get("result", {}).get("featureCollection", {}).get("features", [])
            if not features:
                return None

            return features[0].get("properties", {})

        except Exception as e:
            logger.error(f"산지 판정 조회 실패: {e}")
            return None

    async def is_mountain_area(self, latitude: float, longitude: float, radius_km: float = 5.0) -> bool:
        """
        해당 좌표가 산림입지(산지)인지 확인

        Returns:
            True if mountain area, False otherwise
        """
        mountain_info = await self.get_mountain_info(latitude, longitude, radius_km)
        return mountain_info is not None

    async def get_mountain_height(self, latitude: float, longitude: float) -> Optional[float]:
        """
        산 높이 조회 — VWorld 산림입지도는 높이 속성을 제공하지 않는다.
        경사도 계산(risk_assessment_service._calculate_slope)은 이 값이 None이어도
        DEM 기반 폴백 로직으로 정상 동작한다.

        Returns:
            항상 None (높이 데이터 소스 없음 — 추정치를 임의로 만들어내지 않음)
        """
        return None
