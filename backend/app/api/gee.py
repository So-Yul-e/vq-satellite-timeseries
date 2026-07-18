"""Google Earth Engine API 엔드포인트"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.core.security import get_current_user
from app.services.gee_service import GEEService

router = APIRouter()
gee_service = GEEService()


class ImageSearchRequest(BaseModel):
    latitude: float
    longitude: float
    buffer_km: float = 5.0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    max_cloud_cover: int = 20
    vis_preset: str = 'true_color'
    comparison_date: Optional[str] = None # For Time Series Change Detection
    source: str = 'sentinel-2' # 'sentinel-2' or 'sentinel-1'


class AreaSearchRequest(BaseModel):
    bounds: List[List[float]]  # [[lon, lat], [lon, lat], ...]
    start_date: str
    end_date: str
    max_cloud_cover: int = 20
    limit: int = 10


@router.get("/status")
async def gee_status(current_user=Depends(get_current_user)):
    """GEE 연결 상태 확인"""
    return {
        "initialized": gee_service.initialized,
        "service": "Google Earth Engine",
        "satellite": "Sentinel-2"
    }


@router.post("/search/point")
async def search_by_point(
    request: ImageSearchRequest,
    current_user=Depends(get_current_user),
):
    """
    좌표 기반 위성 영상 검색
    
    Example:
        {
            "latitude": 37.5665,
            "longitude": 126.9780,
            "buffer_km": 10,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "max_cloud_cover": 20,
            "vis_preset": "ndvi"
        }
    """
    try:
        result = gee_service.get_sentinel2_image(
            latitude=request.latitude,
            longitude=request.longitude,
            buffer_km=request.buffer_km,
            start_date=request.start_date,
            end_date=request.end_date,
            max_cloud_cover=request.max_cloud_cover,
            vis_preset=request.vis_preset,
            comparison_date=request.comparison_date,
            source=request.source
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/area")
async def search_by_area(
    request: AreaSearchRequest,
    current_user=Depends(get_current_user),
):
    """
    영역 기반 위성 영상 검색
    
    Example:
        {
            "bounds": [
                [126.9, 37.5],
                [127.1, 37.5],
                [127.1, 37.6],
                [126.9, 37.6],
                [126.9, 37.5]
            ],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "max_cloud_cover": 20,
            "limit": 10
        }
    """
    try:
        results = gee_service.search_images(
            bounds=request.bounds,
            start_date=request.start_date,
            end_date=request.end_date,
            max_cloud_cover=request.max_cloud_cover,
            limit=request.limit
        )
        return {
            "success": True,
            "count": len(results),
            "images": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{image_id}")
async def get_download_url(
    image_id: str,
    bounds: str,  # JSON string: [[lon,lat], ...]
    scale: int = 10,
    current_user=Depends(get_current_user),
):
    """
    영상 다운로드 URL 생성
    
    Args:
        image_id: GEE 영상 ID (예: COPERNICUS/S2_SR_HARMONIZED/20240101T012345_20240101T012345_T52SDG)
        bounds: 영역 좌표 (JSON 문자열)
        scale: 해상도 (미터, 기본 10m)
    """
    try:
        import json
        bounds_list = json.loads(bounds)
        
        url = gee_service.download_image(
            image_id=image_id,
            bounds=bounds_list,
            scale=scale
        )
        
        return {
            "success": True,
            "download_url": url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
