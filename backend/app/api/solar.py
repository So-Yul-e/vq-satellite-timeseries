
import logging
import math
import uuid
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from geoalchemy2 import Geography, Geometry
from geoalchemy2.elements import WKTElement
from app.core.database import get_db
from app.core.security import get_current_user
from app.services.solar_service import SolarService
from app.services.vworld_service import vworld_service, tile_centers
from app.services.solar_detection_service import solar_detection_service, pixel_detections_to_geo
from app.services.panel_permit_matching_service import PanelPermitMatchingService
from app.models.satellite import Satellite
from app.models.solar_panel import SolarPanel
from pydantic import BaseModel
from typing import List, Optional

logger = logging.getLogger(__name__)

router = APIRouter()
solar_service = SolarService()

# 탐지 저장 시 satellite_id(FK NOT NULL)를 채우기 위한 고정 출처 레코드 마커.
# VWorld 항공영상은 파일 업로드가 아니므로 file_path에 상수 마커를 넣는다.
_VWORLD_AERIAL_FILE_PATH = "vworld-aerial://ortho"

# 같은 위치 재탐지 시 중복 저장을 막기 위한 근접 판정 반경(m)
_DEDUP_RADIUS_M = 10.0


def _get_or_create_vworld_satellite(db: Session, user_id) -> Satellite:
    """VWorld 항공영상 출처를 나타내는 satellites 레코드를 get-or-create 한다.

    solar_panels.satellite_id가 NOT NULL FK라 실제 업로드된 위성영상이 없는
    /api/solar/analyze(VWorld 온디맨드 조회) 경로에서도 저장하려면 대표 레코드가 필요하다.
    """
    satellite = (
        db.query(Satellite)
        .filter(Satellite.file_path == _VWORLD_AERIAL_FILE_PATH)
        .first()
    )
    if satellite is not None:
        return satellite

    satellite = Satellite(
        user_id=user_id,
        file_path=_VWORLD_AERIAL_FILE_PATH,
        status="completed",
        metadata_json={"source": "VWORLD-AERIAL", "note": "온디맨드 항공영상 탐지 대표 레코드"},
    )
    db.add(satellite)
    try:
        db.commit()
        db.refresh(satellite)
    except Exception:
        # 동시 요청으로 이미 생성됐을 수 있음 — 재조회로 복구
        db.rollback()
        satellite = (
            db.query(Satellite)
            .filter(Satellite.file_path == _VWORLD_AERIAL_FILE_PATH)
            .first()
        )
        if satellite is None:
            raise
    return satellite


def _bbox_polygon_geojson(lat: float, lng: float, area_m2: float) -> dict:
    """중심 좌표 + 면적으로 근사한 정사각형 bbox를 GeoJSON Polygon으로 만든다.

    pixel_detections_to_geo가 bbox 4코너를 넘겨주지 않으므로(중심점 + area_m2만 존재),
    면적과 같은 넓이의 정사각형을 중심 기준으로 만들어 4코너 폴리곤을 근사한다.
    """
    side_m = max(area_m2, 1.0) ** 0.5
    half_lat_deg = (side_m / 2.0) / 111_000.0
    half_lng_deg = (side_m / 2.0) / (111_000.0 * max(math.cos(math.radians(lat)), 1e-6))

    n, s = lat + half_lat_deg, lat - half_lat_deg
    e, w = lng + half_lng_deg, lng - half_lng_deg

    return {
        "type": "Polygon",
        "coordinates": [[
            [w, n], [e, n], [e, s], [w, s], [w, n],
        ]],
    }


def _find_existing_panel_nearby(db: Session, lat: float, lng: float) -> Optional[SolarPanel]:
    """~10m 이내 기존 solar_panels 레코드가 있으면 반환한다 (중복 저장 방지)."""
    point = WKTElement(f"POINT({lng} {lat})", srid=4326)
    panel_geog = func.cast(func.cast(SolarPanel.geom, Geometry), Geography)
    target_geog = func.cast(func.cast(point, Geometry), Geography)

    return (
        db.query(SolarPanel)
        .filter(SolarPanel.geom.isnot(None))
        .filter(func.ST_DWithin(panel_geog, target_geog, _DEDUP_RADIUS_M))
        .order_by(func.ST_Distance(panel_geog, target_geog))
        .first()
    )


def _persist_detection(
    db: Session,
    satellite: Satellite,
    det: dict,
    permit_info: dict,
    permit_service: "PanelPermitMatchingService",
) -> Optional[SolarPanel]:
    """탐지 1건을 solar_panels(+panel_permit_matches)에 저장한다.

    실패해도 예외를 상위로 던지지 않는다 — 저장 실패가 분석 응답 자체를
    죽이면 안 되므로 호출부에서 try/except로 감싸 로깅만 하고 넘어간다.
    """
    lat = det.get("latitude", 0.0)
    lng = det.get("longitude", 0.0)
    area_m2 = det.get("area_m2", 0.0)
    confidence = det.get("confidence", 0.0)
    metadata = det.get("metadata_json", {}) or {}

    is_legal = permit_info.get("is_legal")
    has_permit = permit_info.get("has_permit")
    status = "detected"
    if has_permit and is_legal:
        status = "legal_confirmed"
    elif has_permit is False:
        status = "illegal_confirmed"

    existing = _find_existing_panel_nearby(db, lat, lng)
    if existing is not None:
        # 재탐지 — 새 row를 만들지 않고 신뢰도/상태만 갱신
        existing.detection_confidence = confidence
        existing.is_legal = is_legal
        existing.status = status
        existing.metadata_json = {
            **(existing.metadata_json or {}),
            **metadata,
        }
        db.commit()
        db.refresh(existing)
        panel = existing
    else:
        panel = SolarPanel(
            satellite_id=satellite.id,
            center_latitude=lat,
            center_longitude=lng,
            geom=WKTElement(f"POINT({lng} {lat})", srid=4326),
            panel_polygon=_bbox_polygon_geojson(lat, lng, area_m2),
            area_m2=area_m2,
            detection_confidence=confidence,
            status=status,
            is_legal=is_legal,
            metadata_json=metadata,
        )
        db.add(panel)
        db.commit()
        db.refresh(panel)

    # 허가 매칭 결과를 panel_permit_matches에도 기록 (좌표 매칭 결과 재사용, 재계산 안 함)
    nearest_permit_id = permit_info.get("nearest_permit_id")
    if nearest_permit_id:
        try:
            permit_service.save_match_result(
                panel_id=panel.id,
                permit_id=uuid.UUID(nearest_permit_id),
                distance_m=permit_info.get("nearest_permit_distance_m") or 0.0,
                match_type=permit_info.get("match_type", "suspected_illegal"),
                match_confidence=permit_info.get("match_confidence", 0.0) or 0.0,
                area_ratio=None,
            )
        except Exception:
            logger.error("패널-허가 매칭 저장 실패 (panel_id=%s)", panel.id, exc_info=True)

    return panel

class SolarDataPoint(BaseModel):
    region: str # metcoRegNm (e.g., 광주시, 대구시)
    date: str # tradeYmd
    hour: str # tradeHour
    amount: float # amount (amount of power)

class SolarResponse(BaseModel):
    success: bool
    data: List[SolarDataPoint]
    total_amount: float
    message: Optional[str] = None

@router.get("/generation", response_model=SolarResponse)
async def get_generation(
    date: str = Query(..., description="Target date in YYYY-MM-DD format"),
    current_user=Depends(get_current_user),
):
    """
    Get solar power generation data for a specific date.
    Converts YYYY-MM-DD to YYYYMMDD for the public API.
    """
    try:
        # Convert YYYY-MM-DD to YYYYMMDD
        trade_ymd = date.replace("-", "")
        
        raw_data = await solar_service.get_daily_generation(trade_ymd)
        
        processed_data = []
        total_gen = 0.0
        
        for item in raw_data:
            # item keys: metcoRegNm, tradeYmd, tradeHour, amount
            region = item.get("metcoRegNm", "Unknown")
            hour = str(item.get("tradeHour", "00"))
            amount = float(item.get("amount", 0))
            
            processed_data.append(SolarDataPoint(
                region=region,
                date=item.get("tradeYmd"),
                hour=hour,
                amount=amount
            ))
            total_gen += amount
            
        return SolarResponse(
            success=True,
            data=processed_data,
            total_amount=total_gen
        )

    except Exception as e:
        logger.error("Error processing solar data: %s", e, exc_info=True)
        return SolarResponse(success=False, data=[], total_amount=0, message=str(e))


class Bounds(BaseModel):
    north: float
    south: float
    east: float
    west: float


class AnalyzeRequest(BaseModel):
    latitude: float
    longitude: float
    buffer_km: float = 5.0
    # 지도 가시영역(bounds)이 오면 그 범위를 고해상도 타일로 나눠 전부 탐지한다.
    # 없으면 중심 좌표 + buffer_km 단일 영상만 탐지(하위 호환).
    bounds: Bounds | None = None


def _dedup_geo_detections(dets: list[dict], min_dist_m: float = 8.0) -> list[dict]:
    """타일 경계에서 중복 탐지된 패널을 근접 좌표 기준으로 제거한다."""
    kept: list[dict] = []
    for d in dets:
        dup = False
        for k in kept:
            # 위경도 1도 ≈ 111km, 대략적 근접 판정으로 충분
            dlat = (d["latitude"] - k["latitude"]) * 111000.0
            dlng = (d["longitude"] - k["longitude"]) * 111000.0 * math.cos(math.radians(d["latitude"]))
            if (dlat * dlat + dlng * dlng) ** 0.5 < min_dist_m:
                dup = True
                break
        if not dup:
            kept.append(d)
    return kept


@router.post("/analyze")
async def analyze_solar_panels(
    request: AnalyzeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    태양광 패널 탐지 분석 (개선 버전 + 허가 확인)

    Args:
        latitude: 위도
        longitude: 경도
        buffer_km: 분석 반경 (km)
        db: 데이터베이스 세션

    Returns:
        탐지 결과 (위성 영상, 탐지된 패널 목록, 품질 점수, 허가 정보 등)
    """
    try:
        # 허가 매칭 서비스 초기화 (SolarPermit 기반, canonical 매칭 경로)
        permit_service = PanelPermitMatchingService(db)

        # 탐지 결과를 solar_panels에 저장하기 위한 대표 satellite 레코드
        # (실패해도 분석 응답 자체는 죽지 않아야 하므로 별도로 감싼다)
        vworld_satellite = None
        try:
            vworld_satellite = _get_or_create_vworld_satellite(db, current_user.id)
        except Exception:
            logger.error("VWorld 대표 satellite 레코드 get-or-create 실패", exc_info=True)

        def _detect_ortho(ortho) -> list[dict]:
            px = solar_detection_service.detect(ortho["image"], conf=0.2)
            return pixel_detections_to_geo(
                px,
                bbox=ortho["bbox"],
                width_px=ortho["width_px"],
                height_px=ortho["height_px"],
                meters_per_pixel_x=ortho["meters_per_pixel_x"],
                meters_per_pixel_y=ortho["meters_per_pixel_y"],
            )

        if request.bounds is not None:
            # 지도 가시영역을 zoom 18 고해상도 타일로 나눠 전부 탐지 후 집계
            b = request.bounds
            centers = tile_centers(
                north=b.north, south=b.south, east=b.east, west=b.west,
                zoom=18, size_px=1024, max_tiles=16,
            )
            geo_detections = []
            for clat, clng in centers:
                ortho = vworld_service.get_ortho_image(latitude=clat, longitude=clng, zoom=18)
                geo_detections.extend(_detect_ortho(ortho))
            geo_detections = _dedup_geo_detections(geo_detections)
        else:
            # 중심 좌표 + buffer 단일 영상(하위 호환)
            ortho = vworld_service.get_ortho_image(
                latitude=request.latitude,
                longitude=request.longitude,
                buffer_km=request.buffer_km,
            )
            geo_detections = _detect_ortho(ortho)

        detections = [
            {
                "latitude": gd["latitude"],
                "longitude": gd["longitude"],
                "area_m2": gd["area_m2"],
                "confidence": gd["confidence"],
                "metadata_json": {
                    "quality_score": round(gd["confidence"] * 100, 1),
                    "detection_method": "yolov8-vworld",
                },
            }
            for gd in geo_detections
        ]

        # 탐지 결과를 프론트엔드 형식으로 변환
        panels = []
        # 응답 내 패널 id 중복 방지 — 원시 dedup(8m)과 기존 패널 매칭(10m) 반경 차이로
        # 서로 다른 탐지 2건이 같은 DB 패널로 수렴하면 같은 id가 응답에 두 번 실려
        # 프론트 React key 충돌·통계 부풀림이 생긴다. 통계는 dedup 후 일괄 계산.
        seen_panel_ids: set = set()

        for det in detections:
            # 허가 확인 (각 패널마다) — SolarPanel row가 아직 없으므로 좌표 기반 매칭 사용
            permit_info = permit_service.match_coordinates_with_permits(
                latitude=det.get("latitude", 0),
                longitude=det.get("longitude", 0),
                area_m2=det.get("area_m2", 0),
                radius_m=100  # 100m 반경 내 허가 검색
            )
            # permit_status 결정 (허가 매칭 결과 기반)
            if permit_info.get("has_permit") and permit_info.get("is_legal"):
                permit_status = "legal"
            elif permit_info.get("has_permit") is False:
                permit_status = "illegal"
            else:
                permit_status = "pending"

            # 메타데이터에서 품질 점수 추출
            metadata = det.get("metadata_json", {})
            if isinstance(metadata, str):
                import json
                try:
                    metadata = json.loads(metadata)
                except:
                    metadata = {}

            quality_score = metadata.get("quality_score", det.get("quality_score", 0))

            # 품질 등급 분류
            if quality_score >= 70:
                quality_level = "high"
            elif quality_score >= 50:
                quality_level = "medium"
            else:
                quality_level = "low"

            # DB 영속화 — 실패해도 탐지 응답 자체는 정상 반환한다.
            saved_panel_id = det.get("id", "")
            if vworld_satellite is not None:
                try:
                    saved = _persist_detection(
                        db=db,
                        satellite=vworld_satellite,
                        det=det,
                        permit_info=permit_info,
                        permit_service=permit_service,
                    )
                    if saved is not None:
                        saved_panel_id = str(saved.id)
                except Exception:
                    logger.error("탐지 결과 DB 저장 실패 (lat=%s, lng=%s)", det.get("latitude"), det.get("longitude"), exc_info=True)
                    db.rollback()

            # 같은 DB 패널로 수렴한 재탐지는 응답에 한 번만 (React key·통계 정합)
            if saved_panel_id and saved_panel_id in seen_panel_ids:
                continue
            if saved_panel_id:
                seen_panel_ids.add(saved_panel_id)

            panel = {
                "id": saved_panel_id,
                "latitude": det.get("latitude", 0.0),
                "longitude": det.get("longitude", 0.0),
                "area": det.get("area_m2", 0.0),
                "confidence": det.get("confidence", 0.0),
                "permit_status": permit_status,
                "quality_score": quality_score,
                "quality_level": quality_level,
                "detection_method": metadata.get("detection_method", "unknown"),
                "permit_info": permit_info  # 허가 상세 정보 추가
            }
            panels.append(panel)

        # 통계는 dedup된 최종 panels 기준으로 일괄 계산 (중복 시 부풀림 방지)
        legal_count = sum(1 for p in panels if p["permit_status"] == "legal")
        illegal_count = sum(1 for p in panels if p["permit_status"] == "illegal")
        pending_count = sum(1 for p in panels if p["permit_status"] == "pending")
        high_quality_count = sum(1 for p in panels if p["quality_level"] == "high")
        medium_quality_count = sum(1 for p in panels if p["quality_level"] == "medium")
        low_quality_count = sum(1 for p in panels if p["quality_level"] == "low")
        avg_quality = sum(p["quality_score"] for p in panels) / len(panels) if panels else 0
        avg_confidence = sum(p["confidence"] for p in panels) / len(panels) if panels else 0

        # 허가 통계 추가 정보
        permit_stats = permit_service.get_permit_statistics()

        # 결과 포맷팅
        return {
            "success": True,
            "detection": {
                "total_panels": len(panels),
                "panels": panels,
                "legal": legal_count,
                "illegal": illegal_count,
                "pending": pending_count,
                "quality_stats": {
                    "high": high_quality_count,
                    "medium": medium_quality_count,
                    "low": low_quality_count,
                    "average_score": round(avg_quality, 1),
                    "average_confidence": round(avg_confidence * 100, 1)
                }
            },
            "permit_stats": permit_stats,  # 허가 통계 추가
            "satellite_image": {
                "source": "vworld-photo",
                "bbox": ortho["bbox"],
                "width_px": ortho["width_px"],
                "height_px": ortho["height_px"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error analyzing solar panels: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="분석 중 오류가 발생했습니다")
