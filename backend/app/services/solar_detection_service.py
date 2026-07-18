from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import List, Optional, TypedDict, Union

import numpy as np

logger = logging.getLogger(__name__)


class GeoDetection(TypedDict):
    latitude: float
    longitude: float
    area_m2: float
    confidence: float

# 컨테이너 기준 절대 경로: backend/app/services/ -> backend/models/
_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "yolov8_solar_panels.pt"
_HF_REPO_ID = "finloop/yolov8s-seg-solar-panels"
_HF_FILENAME = "best.pt"


class Detection(TypedDict):
    bbox_px: List[float]  # [x1, y1, x2, y2]
    confidence: float
    area_px: int
    mask_area_px: int


class SolarDetectionService:
    """YOLOv8-seg 기반 태양광 패널 탐지 서비스 (lazy-load 싱글톤)."""

    _instance: Optional["SolarDetectionService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "SolarDetectionService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._model = None
        return cls._instance

    def _ensure_model_file(self) -> Path:
        """모델 파일이 없으면 HuggingFace Hub에서 다운로드."""
        if _MODEL_PATH.exists():
            return _MODEL_PATH

        logger.warning(
            "YOLOv8 태양광 모델을 %s 에서 찾지 못해 HuggingFace Hub(%s)에서 다운로드합니다.",
            _MODEL_PATH,
            _HF_REPO_ID,
        )
        from huggingface_hub import hf_hub_download

        downloaded_path = hf_hub_download(repo_id=_HF_REPO_ID, filename=_HF_FILENAME)
        # 다운로드된 캐시 경로를 그대로 반환 (원본 위치로 복사하지 않음)
        return Path(downloaded_path)

    def _get_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from ultralytics import YOLO

                    model_path = self._ensure_model_file()
                    logger.info("YOLOv8 태양광 탐지 모델 로딩: %s", model_path)
                    self._model = YOLO(str(model_path))
        return self._model

    def detect(
        self,
        image_bgr_or_path: Union[np.ndarray, str, Path],
        conf: float = 0.25,
    ) -> List[Detection]:
        """이미지에서 태양광 패널을 탐지해 픽셀 공간 결과 리스트를 반환한다.

        Args:
            image_bgr_or_path: OpenCV BGR ndarray 또는 이미지 파일 경로
            conf: confidence threshold

        Returns:
            [{bbox_px, confidence, area_px, mask_area_px}, ...]
        """
        model = self._get_model()

        results = model.predict(image_bgr_or_path, conf=conf, verbose=False)
        if not results:
            return []

        result = results[0]
        detections: List[Detection] = []

        if result.boxes is None or len(result.boxes) == 0:
            return detections

        boxes_xyxy = result.boxes.xyxy.cpu().numpy()
        confidences = result.boxes.conf.cpu().numpy()

        # 마스크는 모델 입력 해상도 기준이므로 원본 이미지 크기로 리사이즈해 면적을 계산한다.
        masks_data = None
        if result.masks is not None:
            masks_data = result.masks.data.cpu().numpy()  # (N, mh, mw)
            orig_h, orig_w = result.orig_shape

        for i in range(len(boxes_xyxy)):
            x1, y1, x2, y2 = boxes_xyxy[i].tolist()
            area_px = int(max(0.0, (x2 - x1)) * max(0.0, (y2 - y1)))

            mask_area_px = area_px
            if masks_data is not None:
                mask = masks_data[i]
                if mask.shape != (orig_h, orig_w):
                    import cv2

                    mask = cv2.resize(
                        mask.astype(np.float32),
                        (orig_w, orig_h),
                        interpolation=cv2.INTER_NEAREST,
                    )
                mask_area_px = int((mask > 0.5).sum())

            detections.append(
                Detection(
                    bbox_px=[float(x1), float(y1), float(x2), float(y2)],
                    confidence=float(confidences[i]),
                    area_px=area_px,
                    mask_area_px=mask_area_px,
                )
            )

        return detections


# 모듈 레벨 싱글톤 인스턴스 (다른 서비스에서 바로 import해서 사용)
solar_detection_service = SolarDetectionService()


def pixel_detections_to_geo(
    detections: List[Detection],
    bbox: dict,
    width_px: int,
    height_px: int,
    meters_per_pixel_x: float,
    meters_per_pixel_y: float,
) -> List[GeoDetection]:
    """픽셀 공간 탐지 결과를 위경도 좌표 + 실면적(m²)으로 변환한다.

    bbox는 {"north", "south", "east", "west"} 형태(EPSG:4326)를 기대하며,
    이미지 좌상단이 (west, north), 우하단이 (east, south)에 대응한다고 가정한다.

    Args:
        detections: solar_detection_service.detect()의 픽셀 공간 결과
        bbox: 영상의 지리적 경계
        width_px: 영상 가로 픽셀 수
        height_px: 영상 세로 픽셀 수
        meters_per_pixel_x: 가로 방향 미터/픽셀
        meters_per_pixel_y: 세로 방향 미터/픽셀

    Returns:
        [{latitude, longitude, area_m2, confidence}, ...]
    """
    north, south = bbox["north"], bbox["south"]
    east, west = bbox["east"], bbox["west"]

    geo_detections: List[GeoDetection] = []
    for det in detections:
        x1, y1, x2, y2 = det["bbox_px"]
        center_x_px = (x1 + x2) / 2.0
        center_y_px = (y1 + y2) / 2.0

        # 픽셀 x: 0(west) ~ width_px(east), 픽셀 y: 0(north) ~ height_px(south)
        lng = west + (center_x_px / width_px) * (east - west)
        lat = north - (center_y_px / height_px) * (north - south)

        area_m2 = det["mask_area_px"] * meters_per_pixel_x * meters_per_pixel_y

        geo_detections.append(
            GeoDetection(
                latitude=float(lat),
                longitude=float(lng),
                area_m2=float(area_m2),
                confidence=det["confidence"],
            )
        )

    return geo_detections


def detect_solar_geo(latitude: float, longitude: float, buffer_km: float) -> List[dict]:
    """중심 좌표 + 반경 영역에서 태양광 패널을 탐지해 위경도 목록을 반환한다.

    VQ 시계열 변화탐지의 **의미 라벨(YOLO 교차참조)** 용. VQ는 Sentinel-2(10m/px)로
    변화를 잡지만, YOLO 태양광 모델은 고해상 항공영상(VWorld)으로 학습됐으므로
    Sentinel-2 위에 직접 돌리지 않고, **같은 좌표의 VWorld 고해상 타일**에 YOLO를
    돌려 패널 좌표를 얻는다(정직한 교차참조 — 각 모델을 native 해상도에서 사용).

    반경이 크면 zoom18 타일이 많아지므로 최대 16타일로 제한(부분 커버리지 가능).
    실패(VWorld/YOLO 오류)해도 예외를 올리지 않고 빈 리스트 반환(호출부가 best-effort).

    Returns: [{"latitude", "longitude", "confidence"}, ...]
    """
    try:
        from app.services.vworld_service import vworld_service, tile_centers

        latD = buffer_km / 111.0
        lngD = buffer_km / (111.0 * max(0.1, __import__("math").cos(latitude * 3.141592653589793 / 180.0)))
        north, south = latitude + latD, latitude - latD
        east, west = longitude + lngD, longitude - lngD

        centers = tile_centers(north=north, south=south, east=east, west=west,
                               zoom=18, size_px=1024, max_tiles=16)
        out: List[dict] = []
        for clat, clng in centers:
            try:
                ortho = vworld_service.get_ortho_image(latitude=clat, longitude=clng, zoom=18)
                px = solar_detection_service.detect(ortho["image"], conf=0.2)
                geo = pixel_detections_to_geo(
                    px, bbox=ortho["bbox"],
                    width_px=ortho["width_px"], height_px=ortho["height_px"],
                    meters_per_pixel_x=ortho["meters_per_pixel_x"],
                    meters_per_pixel_y=ortho["meters_per_pixel_y"],
                )
                out.extend({"latitude": g["latitude"], "longitude": g["longitude"], "confidence": g["confidence"]} for g in geo)
            except Exception as e:
                logger.warning("타일(%.4f,%.4f) 태양광 탐지 실패(건너뜀): %s", clat, clng, e)
        return out
    except Exception as e:
        logger.warning("detect_solar_geo 실패(비치명적): %s", e)
        return []
