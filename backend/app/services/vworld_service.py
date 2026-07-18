from __future__ import annotations

import logging
import math
from typing import TypedDict

import cv2
import numpy as np
import requests
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

_VWORLD_IMAGE_URL = "https://api.vworld.kr/req/image"
_DEFAULT_IMAGE_SIZE = 1024  # px, 정사각 출력
_EARTH_RADIUS_M = 6378137.0
_TILE_SIZE = 256
# z0에서의 웹 메르카토르 해상도(m/px) = 2πR / 256 ≈ 156543.034
_INITIAL_RES = 2 * math.pi * _EARTH_RADIUS_M / _TILE_SIZE
_MIN_ZOOM = 15
_MAX_ZOOM = 19  # VWorld 항공영상 최대 상세 수준(패널 탐지 가능 해상도)


def _lnglat_to_merc(lng: float, lat: float) -> tuple[float, float]:
    x = math.radians(lng) * _EARTH_RADIUS_M
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * _EARTH_RADIUS_M
    return x, y


def _merc_to_lnglat(x: float, y: float) -> tuple[float, float]:
    lng = math.degrees(x / _EARTH_RADIUS_M)
    lat = math.degrees(2 * math.atan(math.exp(y / _EARTH_RADIUS_M)) - math.pi / 2)
    return lng, lat


def _resolution(zoom: int) -> float:
    """해당 zoom의 웹 메르카토르 해상도(m/px)."""
    return _INITIAL_RES / (2 ** zoom)


def _zoom_for(buffer_km: float, size_px: int) -> int:
    """원하는 지상 폭(2*buffer_km)을 size_px에 담는 zoom을 고르고 상세 범위로 clamp."""
    target_res = max((2.0 * buffer_km * 1000.0) / size_px, 1e-6)
    zoom = math.log2(_INITIAL_RES / target_res)
    return max(_MIN_ZOOM, min(_MAX_ZOOM, round(zoom)))


def tile_centers(
    north: float,
    south: float,
    east: float,
    west: float,
    zoom: int,
    size_px: int,
    max_tiles: int = 16,
) -> list[tuple[float, float]]:
    """bbox를 zoom/size 기준 고해상도 타일들로 나눈 각 타일 중심(lat,lng) 목록.

    타일 수가 max_tiles를 넘으면 bbox 중앙 영역만 커버하도록 격자를 줄인다
    (넓은 영역을 저해상도로 뭉개는 대신, 상세 해상도를 유지하고 중앙에 집중).
    """
    minx, miny = _lnglat_to_merc(west, south)
    maxx, maxy = _lnglat_to_merc(east, north)
    cx0, cy0 = (minx + maxx) / 2.0, (miny + maxy) / 2.0

    tile_m = size_px * _resolution(zoom)  # 타일 하나가 덮는 메르카토르 거리(m)
    nx = max(1, math.ceil((maxx - minx) / tile_m))
    ny = max(1, math.ceil((maxy - miny) / tile_m))

    # max_tiles 초과 시 격자 축소(중앙 집중)
    while nx * ny > max_tiles:
        if nx >= ny and nx > 1:
            nx -= 1
        elif ny > 1:
            ny -= 1
        else:
            break

    centers: list[tuple[float, float]] = []
    for j in range(ny):
        for i in range(nx):
            # 격자를 중앙(cx0,cy0) 기준으로 배치
            x = cx0 + (i - (nx - 1) / 2.0) * tile_m
            y = cy0 + (j - (ny - 1) / 2.0) * tile_m
            lng, lat = _merc_to_lnglat(x, y)
            centers.append((lat, lng))
    return centers


class BBox(TypedDict):
    north: float
    south: float
    east: float
    west: float


class OrthoImageResult(TypedDict):
    image: np.ndarray  # BGR
    bbox: BBox
    width_px: int
    height_px: int
    meters_per_pixel_x: float
    meters_per_pixel_y: float


class VWorldService:
    """VWorld(브이월드) 항공정사영상 Image API 클라이언트."""

    def __init__(self) -> None:
        self.api_key = settings.VWORLD_API_KEY
        self.image_size = _DEFAULT_IMAGE_SIZE

    def _require_api_key(self) -> None:
        if not self.api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="VWorld API 키가 설정되지 않았습니다",
            )

    def get_ortho_image(
        self,
        latitude: float,
        longitude: float,
        buffer_km: float = 1.0,
        zoom: int | None = None,
    ) -> OrthoImageResult:
        """VWorld 항공정사영상(PHOTO 베이스맵)을 bbox 기준으로 가져온다.

        Args:
            latitude: 중심 위도
            longitude: 중심 경도
            buffer_km: 중심에서 각 방향으로의 반경(km)

        Returns:
            OrthoImageResult (image, bbox, 픽셀 크기, 미터/픽셀 환산값)

        Raises:
            HTTPException: API 키 미설정(503) 또는 VWorld 호출 실패(502)
        """
        self._require_api_key()

        # VWorld Image API는 center+zoom 방식을 요구한다(bbox 아님).
        # 웹 메르카토르(EPSG:900913)로 요청해 zoom↔해상도 계산을 정확히 맞춘다.
        if zoom is None:
            zoom = _zoom_for(buffer_km, self.image_size)
        zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, int(zoom)))
        cx, cy = _lnglat_to_merc(longitude, latitude)

        params = {
            "service": "image",
            "request": "getmap",
            "format": "png",
            "basemap": "PHOTO",
            "crs": "EPSG:900913",
            "center": f"{cx},{cy}",
            "zoom": str(zoom),
            "size": f"{self.image_size},{self.image_size}",
            "key": self.api_key,
        }

        try:
            response = requests.get(_VWORLD_IMAGE_URL, params=params, timeout=20)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error("VWorld Image API 호출 실패: %s", e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="VWorld 영상 조회 중 오류가 발생했습니다",
            ) from e

        content_type = response.headers.get("Content-Type", "")
        if "image" not in content_type:
            logger.error(
                "VWorld Image API가 이미지가 아닌 응답을 반환했습니다 (Content-Type=%s): %s",
                content_type,
                response.text[:300],
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="VWorld 영상 조회 중 오류가 발생했습니다",
            )

        image_array = np.frombuffer(response.content, dtype=np.uint8)
        image_bgr = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if image_bgr is None:
            logger.error("VWorld 응답 이미지를 디코딩하지 못했습니다")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="VWorld 영상 조회 중 오류가 발생했습니다",
            )

        actual_height, actual_width = image_bgr.shape[:2]

        # 좌하단 "VWORLD" 파란 로고 워터마크가 YOLO에 패널로 오탐되므로 마스킹한다
        # (로고는 약 110x30px — 여유를 두고 지운다)
        logo_h, logo_w = 45, 140
        image_bgr[actual_height - logo_h:actual_height, 0:logo_w] = 0

        # center+zoom+size로 실제 영상이 덮는 메르카토르 범위를 계산하고 위경도 bbox로 변환한다.
        res = _resolution(zoom)  # m/px (웹 메르카토르)
        half_w_m = (actual_width / 2.0) * res
        half_h_m = (actual_height / 2.0) * res
        west_lng, north_lat = _merc_to_lnglat(cx - half_w_m, cy + half_h_m)
        east_lng, south_lat = _merc_to_lnglat(cx + half_w_m, cy - half_h_m)
        bbox = BBox(north=north_lat, south=south_lat, east=east_lng, west=west_lng)

        # 실지상 해상도 = 메르카토르 해상도 × cos(lat) (면적 환산용)
        ground_res = res * math.cos(math.radians(latitude))
        meters_per_pixel_x = ground_res
        meters_per_pixel_y = ground_res

        return OrthoImageResult(
            image=image_bgr,
            bbox=bbox,
            width_px=actual_width,
            height_px=actual_height,
            meters_per_pixel_x=meters_per_pixel_x,
            meters_per_pixel_y=meters_per_pixel_y,
        )


# 모듈 레벨 싱글톤 인스턴스
vworld_service = VWorldService()
