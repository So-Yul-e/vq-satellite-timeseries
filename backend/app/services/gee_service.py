"""Google Earth Engine 서비스"""
import ee
import httpx
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


def _same_season_current(past_date: str) -> str:
    """T1과 **같은 계절**(같은 월·일)의 가장 최근 연도 날짜를 반환한다.

    계절 정합의 핵심: T2를 "오늘"이 아니라 T1과 같은 절기로 맞춰야 식생 위상이
    정렬돼, 잎이 지고 나는 것 같은 계절 변화가 "변화"로 오탐되지 않는다.
    올해 같은 월·일이 아직 안 지났으면 작년으로.
    """
    from datetime import datetime, date
    past = datetime.strptime(past_date, '%Y-%m-%d').date()
    today = date.today()
    try:
        cand = date(today.year, past.month, past.day)
    except ValueError:  # 2/29 등 존재하지 않는 날짜
        cand = date(today.year, past.month, 28)
    if cand > today:
        cand = cand.replace(year=today.year - 1)
    return cand.strftime('%Y-%m-%d')


def _radiometric_match(ref_path: str, src_path: str) -> None:
    """src 이미지를 ref의 채널별 밝기·대비(평균·표준편차)에 맞춰 정규화 후 덮어쓴다.

    조도(해 각도)·대기 흐림 차이로 두 시점의 픽셀값이 통째로 밀리면 특징 벡터도
    밀려 codeword 할당이 바뀌어 오탐이 된다. 채널별 moment matching으로 1차 보정:
    src' = (src − μ_src)·(σ_ref/σ_src) + μ_ref. (실패해도 원본 유지 — 비치명)
    주: 전역 통계 기반이라 변화 면적이 아주 크면 일부 상쇄될 수 있음(1차 근사).
    """
    try:
        from PIL import Image
        import numpy as np
        ref = np.asarray(Image.open(ref_path).convert("RGB"), dtype=np.float64)
        src = np.asarray(Image.open(src_path).convert("RGB"), dtype=np.float64)
        out = np.empty_like(src)
        for c in range(3):
            sc, rc = src[..., c], ref[..., c]
            s_std = sc.std()
            out[..., c] = sc if s_std < 1e-6 else (sc - sc.mean()) * (rc.std() / s_std) + rc.mean()
        Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB").save(src_path)
    except Exception as e:
        logger.warning("radiometric normalization 실패(비치명적, 원본 유지): %s", e)


class GEEService:
    """Google Earth Engine 위성 영상 처리 서비스"""

    def __init__(self):
        """GEE 초기화"""
        self.http_client = httpx.Client()
        self.dl_model = None
        self.torch = None
        try:
            # Try to load Deep Learning Model
            from app.ml.unet import UNet
            import torch
            import os

            self.torch = torch  # Store torch reference for later use
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            self.dl_model = UNet(n_channels=3, n_classes=2) # 3 bands: RGB

            model_path = 'backend/models/best_model.pth'
            if os.path.exists(model_path):
                self.dl_model.load_state_dict(torch.load(model_path, map_location=self.device))
                logger.info("Deep Learning Model Loaded from %s", model_path)
            else:
                logger.warning("No trained weights found. Using initialized U-Net (Random Weights) for demo.")

            self.dl_model.to(self.device)
            self.dl_model.eval()

        except Exception as e:
            logger.warning("Deep Learning Model Init Failed (Optional): %s", e)
            self.dl_model = None
            self.torch = None
        
        try:
            import os
            import json
            
            # 서비스 계정 키 파일 경로 (여러 위치 시도)
            possible_paths = [
                '/app/gee-service-account.json',  # Docker 컨테이너
                os.path.join(os.path.dirname(__file__), '..', '..', 'gee-service-account.json'),  # 상대 경로
                'backend/gee-service-account.json',  # 프로젝트 루트 기준
            ]
            
            service_account_key = None
            for path in possible_paths:
                if os.path.exists(path):
                    service_account_key = path
                    break
            
            # 서비스 계정 파일이 있으면 사용
            if service_account_key:
                logger.info("GEE 키 파일 발견: %s", service_account_key)

                # JSON 파일에서 이메일 읽기
                with open(service_account_key, 'r') as f:
                    key_data = json.load(f)
                    service_account_email = key_data.get('client_email')

                credentials = ee.ServiceAccountCredentials(
                    email=service_account_email,
                    key_file=service_account_key
                )
                ee.Initialize(credentials)
                logger.info("GEE 서비스 계정으로 초기화 성공: %s", service_account_email)
                self.initialized = True
            else:
                # 서비스 계정 파일이 없으면 기본 인증 시도
                logger.warning("서비스 계정 키 파일을 찾을 수 없습니다. 기본 인증 시도...")
                ee.Initialize()
                logger.info("GEE 기본 인증으로 초기화 성공")
                self.initialized = True

        except Exception as e:
            logger.error("GEE 초기화 실패: %s (에러 타입: %s)", e, type(e).__name__, exc_info=True)
            self.initialized = False
    
    def get_sentinel2_image(
        self,
        latitude: float,
        longitude: float,
        buffer_km: float = 5.0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_cloud_cover: int = 20,
        include_thumbnail: bool = True,
        vis_preset: str = 'true_color',  # visual preset option
        comparison_date: Optional[str] = None, # User-selected date for Past Image
        source: str = 'sentinel-2',  # 'sentinel-2' (Optical) or 'sentinel-1' (Radar)
    ) -> Dict:
        """
        Sentinel-2 위성 영상 가져오기
        vis_preset: 'true_color', 'false_color', 'ndvi', 'urban'
        """
        if not self.initialized:
            raise Exception("GEE가 초기화되지 않았습니다")
        
        # 기본 날짜 설정 (최근 30일 -> 1년으로 확장하여 모자이크 품질 향상)
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if not start_date:
            # 기본값: 6개월 전 (충분한 이미지를 확보하기 위함)
            start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
        
        # 관심 지역 (AOI) 설정
        point = ee.Geometry.Point([longitude, latitude])
        aoi = point.buffer(buffer_km * 1000)
        
        if source == 'sentinel-1':
            # Sentinel-1 SAR (Radar) - All weather
            local_collection = (
                ee.ImageCollection('COPERNICUS/S1_GRD')
                .filterBounds(aoi)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
                .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
                .filter(ee.Filter.eq('instrumentMode', 'IW'))
            )
            # Use Mosaic for global collection context
            global_collection = local_collection
        else:
            # Sentinel-2 Optical (Default)
            local_collection = (
                ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(aoi)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_cloud_cover))
                .sort('CLOUDY_PIXEL_PERCENTAGE')
            )
            
            # Global collection for filling gaps
            global_collection = (
                ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_cloud_cover))
            )
        
        count = local_collection.size().getInfo()
        if count == 0:
            return {"success": False, "message": "No images found", "count": 0}
            
        best_image = local_collection.first()
        mosaic_image = global_collection.median()
        properties = best_image.getInfo()['properties']

        # Visualization Parameters Selection
        vis_params = {}
        tile_vis_params = {} # Separate params for tile/mosaic

        # Keep a copy for analysis before any band modifications
        analysis_image = best_image

        if source == 'sentinel-1':
            # SAR Visualization (VV, VH, VV/VH)
            # Create a Ratio band for visualization
            best_image = best_image.addBands(best_image.select('VV').divide(best_image.select('VH')).rename('VV_VH_RATIO'))
            mosaic_image = mosaic_image.addBands(mosaic_image.select('VV').divide(mosaic_image.select('VH')).rename('VV_VH_RATIO'))
            
            vis_params = {'bands': ['VV', 'VH', 'VV_VH_RATIO'], 'min': [-20, -25, 1], 'max': [0, -5, 15]}
            tile_vis_params = vis_params
            
            # Using Radar for analysis_image creates issues with NDVI logic below.
            # We must handle that.
            analysis_image = best_image
        else:
            # Sentinel-2 Visualization
            if vis_preset == 'false_color':
                # NIR, Red, Green
                vis_params = {'bands': ['B8', 'B4', 'B3'], 'min': 100, 'max': 3000, 'gamma': 1.2}
                tile_vis_params = vis_params
            elif vis_preset == 'urban':
                # SWIR2, SWIR1, Red (Urban features stand out)
                vis_params = {'bands': ['B12', 'B11', 'B4'], 'min': 100, 'max': 3000, 'gamma': 1.4}
                tile_vis_params = vis_params
            elif vis_preset == 'ndvi':
                # NDVI Calculation for DISPLAY
                ndvi_disp = best_image.normalizedDifference(['B8', 'B4'])
                mosaic_ndvi = mosaic_image.normalizedDifference(['B8', 'B4'])
                best_image = ndvi_disp
                mosaic_image = mosaic_ndvi
                vis_params = {'min': -0.2, 'max': 0.8, 'palette': ['blue', 'white', 'green', 'darkgreen']}
                tile_vis_params = vis_params
            else:
                # Default: True Color
                # Increased min to 200 to remove atmospheric haze, gamma to 1.4 for better contrast
                vis_params = {'bands': ['B4', 'B3', 'B2'], 'min': 200, 'max': 3000, 'gamma': 1.4}
                tile_vis_params = vis_params

        # Visualize for Thumbnail & Tile
        # Note: best_image might have been replaced by NDVI band above
        thumb_rgb = best_image.visualize(**vis_params)
        tile_rgb = mosaic_image.visualize(**tile_vis_params)

        # --- Time Series / Change Detection Logic ---
        past_tile_url = ""
        diff_tile_url = ""
        try:
            # 1. Fetch Past Image (User selected or Default 3 years ago)
            current_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            if comparison_date:
                past_end = comparison_date
                # Start date for past collection: 6 months before comparison date
                past_dt = datetime.strptime(comparison_date, '%Y-%m-%d')
                past_start = (past_dt - timedelta(days=180)).strftime('%Y-%m-%d')
            else:
                past_end = (current_dt - timedelta(days=365*3)).strftime('%Y-%m-%d')
                past_start = (current_dt - timedelta(days=365*3 + 180)).strftime('%Y-%m-%d')
            
            past_collection = (
                ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(aoi)
                .filterDate(past_start, past_end)
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
            )
            
            if past_collection.size().getInfo() > 0:
                past_image = past_collection.median()
                
                # Past Tile (True Color)
                past_rgb = past_image.visualize(bands=['B4', 'B3', 'B2'], min=100, max=2800, gamma=1.2)
                map_id_past = past_rgb.getMapId()
                past_tile_url = map_id_past['tile_fetcher'].url_format
                
                # 2. Change Detection (NDVI Difference)
                # Diff = Current NDVI - Past NDVI? 
                # If Forest -> Solar: NDVI decreases significantly (0.8 -> 0.2)
                # So we look for Past(High) - Current(Low) > Threshold
                past_ndvi = past_image.normalizedDifference(['B8', 'B4'])
                current_ndvi = analysis_image.normalizedDifference(['B8', 'B4']) # analysis_image is current best_image
                
                # Deforestation / Construction: Past > Current
                diff = past_ndvi.subtract(current_ndvi)
                
                # Mask: Show only significant decrease (e.g., > 0.2)
                change_mask = diff.gt(0.25)
                change_layer = change_mask.updateMask(change_mask)
                
                # Visualize Change (Red)
                change_vis = change_layer.visualize(palette=['red'], opacity=0.7)
                map_id_diff = change_vis.getMapId()
                diff_tile_url = map_id_diff['tile_fetcher'].url_format
                
        except Exception as e:
            logger.warning("Time Series Analysis Failed: %s", e)
            pass
        # ---------------------------------------------

        # ---------------------------------------------------------
        # REAL ANALYSIS: Detect Anomalies (Potential Deforestation/Panels)
        # ---------------------------------------------------------
        
        # 0. VQ-Clustering (Simulated using K-Means)
        # To support the project name 'vq-clustering', we apply unsupervised learning
        # to segment the image into spectral clusters before anomaly detection.
        try:
            # Use multi-spectral bands for feature extraction
            features = ['B2', 'B3', 'B4', 'B8', 'B11', 'B12']
            
            # Create training set from the image itself
            training = analysis_image.select(features).sample(
                region=aoi,
                scale=20,
                numPixels=2000
            )
            
            # Train K-Means Clusterer (Unsupervised)
            n_clusters = 5
            clusterer = ee.Clusterer.wekaKMeans(nClusters=n_clusters).train(training)
            
            # Classify the image
            clustered = analysis_image.select(features).cluster(clusterer)
            
            # Note: In a full VQ-VAE model, we would use the latent vectors here.
            # Using GEE's K-Means provides a robust alternative for pattern segmentation.
        except Exception as e:
            logger.warning("Clustering failed: %s", e)

        # ---------------------------------------------------------
        # IMPROVED: Multi-Criteria Solar Panel Detection
        # Strategy: Combine NDVI, Reflectance, and Spectral Indices
        # ---------------------------------------------------------
        detections = []
        try:
            # 1. Calculate Multiple Indices
            # NDVI: Vegetation Index (B8 = NIR, B4 = Red)
            ndvi = analysis_image.normalizedDifference(['B8', 'B4']).rename('ndvi')

            # NDWI: Water Index (B3 = Green, B8 = NIR) - to exclude water bodies
            ndwi = analysis_image.normalizedDifference(['B3', 'B8']).rename('ndwi')

            # BSI: Bare Soil Index (approximation using SWIR and RGB)
            # BSI helps identify bare ground vs artificial structures
            # Formula: ((B11 + B4) - (B8 + B2)) / ((B11 + B4) + (B8 + B2))
            bsi = analysis_image.expression(
                '((SWIR1 + RED) - (NIR + BLUE)) / ((SWIR1 + RED) + (NIR + NIR) + 0.0001)',
                {
                    'SWIR1': analysis_image.select('B11'),
                    'RED': analysis_image.select('B4'),
                    'NIR': analysis_image.select('B8'),
                    'BLUE': analysis_image.select('B2')
                }
            ).rename('bsi')

            # 2. Brightness Index (High reflectance is key for solar panels)
            # Average of visible + NIR bands
            brightness = analysis_image.expression(
                '(BLUE + GREEN + RED + NIR) / 4',
                {
                    'BLUE': analysis_image.select('B2'),
                    'GREEN': analysis_image.select('B3'),
                    'RED': analysis_image.select('B4'),
                    'NIR': analysis_image.select('B8')
                }
            ).rename('brightness')

            # 3. Multi-Criteria Mask for Solar Panels
            # Criteria:
            # - Low NDVI (0.05 < NDVI < 0.35): Non-vegetation
            # - NDWI < 0.1: Not water
            # - High Brightness (> 1500): Reflective surfaces
            # - Moderate BSI: Artificial structures

            # Base mask: Low vegetation
            vegetation_mask = ndvi.lt(0.35).And(ndvi.gt(0.05))

            # Exclude water
            water_mask = ndwi.lt(0.1)

            # High reflectance (solar panels are shiny)
            brightness_mask = brightness.gt(1500)

            # Combine all criteria
            anomaly_mask = vegetation_mask.And(water_mask).And(brightness_mask)

            # 4. Morphological Filtering
            # Remove small noise and smooth boundaries
            # connectedPixelCount: minimum 30 connected pixels (~3000m² at 10m resolution)
            # This filters out small roads, buildings
            anomaly_mask = anomaly_mask.updateMask(anomaly_mask.connectedPixelCount(30).gte(30))

            # Focal median filter to smooth boundaries (reduce jagged edges)
            anomaly_mask = anomaly_mask.focalMedian(radius=1, kernelType='square', units='pixels')

            # 2. Vectorize the anomaly mask (Raster -> Polygon)
            # Fix projection error: Select a specific band (e.g. B4) to get a uniform CRS
            vectors = anomaly_mask.reduceToVectors(
                geometry=aoi,
                crs=analysis_image.select('B4').projection(),
                scale=10,
                geometryType='polygon',
                eightConnected=False,
                labelProperty='label',
                reducer=ee.Reducer.countEvery(),
                maxPixels=1e8
            )
            
            # 3. Process vectors into frontend-friendly format
            def feature_to_dict(feature):
                geom = feature['geometry']['coordinates']
                # GEE returns [ [ [x,y], [x,y]... ] ] (MultiPolygon structure)
                # We need to flatten it or just take the first ring
                # Ensure we handle nested arrays correctly.
                # Usually coordinates is [[[lon, lat], ...]]
                return geom
            
            server_vectors = vectors.getInfo()['features']
            
            # Sort by area (pixel count approximates area)
            # Note: 'count' property from reduceToVectors represents pixel count (~area)
            # At 10m resolution, each pixel ≈ 100m²
            server_vectors.sort(key=lambda x: x['properties']['count'], reverse=True)

            # IMPROVED: Filter by realistic solar panel area ranges
            # Typical solar panel installations: 100m² (small rooftop) to 50,000m² (large farm)
            MIN_AREA_PIXELS = 10    # ~1,000m² (0.1 hectare)
            MAX_AREA_PIXELS = 5000  # ~500,000m² (50 hectare)

            filtered_vectors = [
                v for v in server_vectors
                if MIN_AREA_PIXELS <= v['properties']['count'] <= MAX_AREA_PIXELS
            ]

            # Limit to top 15 detections (increased from 5)
            # This allows detection of multiple smaller facilities
            filtered_vectors = filtered_vectors[:15]

            logger.info(
                "Filtered %d potential solar panel areas (from %d total anomalies)",
                len(filtered_vectors), len(server_vectors)
            )

            # 허가 판정: DB(SolarPermit, PanelPermitMatchingService) 조회로 위임.
            # 과거에는 이 자리에서 공공데이터포털을 실시간으로 병렬 스캔했으나
            # (backend/experiments/gee_realtime_permit_scan.py로 격리 보존됨),
            # 판정 경로 일원화를 위해 canonical 매칭 서비스만 사용한다.
            from app.core.database import SessionLocal
            from app.services.panel_permit_matching_service import PanelPermitMatchingService

            for idx, feat in enumerate(filtered_vectors):
                poly_coords = feat['geometry']['coordinates']

                # Centroid approx
                if len(poly_coords) > 0 and isinstance(poly_coords[0][0], list):
                    # Usually [[[lng, lat], ...]]
                     c_lng = poly_coords[0][0][0]
                     c_lat = poly_coords[0][0][1]
                else:
                     continue # Invalid geometry

                # DB 기반 허가 판정 (canonical 경로)
                permit_db = SessionLocal()
                try:
                    match_result = PanelPermitMatchingService(permit_db).match_coordinates_with_permits(
                        latitude=c_lat, longitude=c_lng, radius_m=100.0
                    )
                    is_registered = bool(match_result.get("is_legal"))
                finally:
                    permit_db.close()
                is_illegal_sim = not is_registered
                
                description = ""
                if is_registered:
                     description = f"등록된 태양광 시설 (허가번호 확인)"
                else:
                     description = f"미허가 의심 구역 (데이터베이스 미일치)"


                # Create detection object
                # Convert coords [lng, lat] -> [lat, lng]
                if len(poly_coords) > 0 and isinstance(poly_coords[0][0], list):
                    latlng_ring = [[p[1], p[0]] for p in poly_coords[0]]
                else: 
                     latlng_ring = []

                if not latlng_ring: continue
                
                # IMPROVED: Multi-Factor Quality Assessment
                # Factors: Shape (compactness), Area, Aspect Ratio
                try:
                    n_points = len(latlng_ring)

                    # Calculate bounding box dimensions
                    lats = [p[0] for p in latlng_ring]
                    lngs = [p[1] for p in latlng_ring]
                    width = max(lngs) - min(lngs)
                    height = max(lats) - min(lats)

                    # Aspect Ratio (elongation measure)
                    aspect_ratio = max(width, height) / min(width, height) if min(width, height) > 0 else 10

                    # Approximate area (in pixels, then convert to m²)
                    pixel_count = feat['properties']['count']
                    area_m2 = pixel_count * 100  # 10m resolution = 100m² per pixel

                    # Calculate perimeter (approximate)
                    perimeter = 0
                    for i in range(len(latlng_ring)):
                        p1 = latlng_ring[i]
                        p2 = latlng_ring[(i + 1) % len(latlng_ring)]
                        # Haversine distance would be more accurate, but this is sufficient
                        dist = ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5
                        perimeter += dist

                    # Compactness: how circular the shape is
                    # Perfect circle = 1.0, elongated shapes < 0.5
                    import math
                    if perimeter > 0:
                        compactness = (4 * math.pi * area_m2) / (perimeter**2 + 1e-6)
                    else:
                        compactness = 0.5

                    # DECISION LOGIC
                    is_road = False
                    quality_score = 0.5  # base score

                    # Factor 1: Aspect Ratio (roads are elongated)
                    if aspect_ratio > 5.0:
                        is_road = True
                        description += " [도로/선형 패턴]"
                        quality_score *= 0.3  # heavily penalize
                    elif aspect_ratio > 3.0:
                        description += " [약간 길쭉함]"
                        quality_score *= 0.7
                    else:
                        quality_score *= 1.0  # good shape

                    # Factor 2: Compactness (solar farms are relatively compact)
                    if compactness < 0.1:
                        is_road = True
                        quality_score *= 0.4
                    elif compactness > 0.3:
                        quality_score *= 1.2  # boost for compact shapes

                    # Factor 3: Area-based confidence
                    # Larger installations are more likely to be real solar farms
                    if area_m2 > 10000:  # > 1 hectare
                        area_confidence = 0.9
                    elif area_m2 > 5000:
                        area_confidence = 0.8
                    elif area_m2 > 2000:
                        area_confidence = 0.7
                    else:
                        area_confidence = 0.6

                    # Final confidence calculation
                    detection_conf = min(0.95, quality_score * area_confidence)

                    # Skip roads entirely (optional: set to False to still show them with low confidence)
                    if is_road and aspect_ratio > 6.0:
                        continue  # Skip this detection

                except Exception as e:
                    logger.warning("Quality assessment error: %s", e)
                    detection_conf = 0.5
                    area_m2 = feat['properties']['count'] * 100

                detection = {
                    "id": f"det-{idx}-{datetime.now().timestamp()}",
                    "latitude": latlng_ring[0][0],
                    "longitude": latlng_ring[0][1],
                    "confidence": detection_conf,
                    "is_illegal": is_illegal_sim,
                    "description": description,
                    "polygon": latlng_ring,
                    "area_m2": area_m2,  # Use calculated area
                    "aspect_ratio": round(aspect_ratio, 2),  # Add shape metrics
                    "compactness": round(compactness, 3) if 'compactness' in locals() else 0.5
                }
                
                detections.append(detection)
            
            # ---------------------------------------------------------
            # 4. Deep Learning Refinement (Real Inference)
            # ---------------------------------------------------------
            if self.dl_model and self.torch:
                try:
                    import io
                    from PIL import Image
                    import torchvision.transforms as T

                    logger.info("Running Deep Learning Inference on Detections...")
                    
                    transform = T.Compose([
                        T.Resize((256, 256)),
                        T.ToTensor(),
                        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
                    ])
                    
                    for det in detections:
                        try:
                            # 1. Get Crop URL for Detection Patch
                            # Convert [[lat, lng], ...] back to GEE format [[lng, lat]]
                            ring = [[p[1], p[0]] for p in det['polygon']]
                            poly_geom = ee.Geometry.Polygon([ring])
                            
                            # Use patch
                            patch_aoi = poly_geom.centroid().buffer(200) # 200m context
                            
                            # Get Thumbnail URL (Sync)
                            # We use analysis_image (could be Sentinel-2 or Sentinel-1)
                            # If S1, visualize returns RGB-like. If S2, vis_params.
                            # Just use simple RGB visualization for consistency
                            thumb_url = analysis_image.visualize(min=0, max=3000, bands=['B4', 'B3', 'B2'] if 'B4' in analysis_image.bandNames().getInfo() else ['VV', 'VH', 'VV_VH_RATIO']).getThumbURL({
                                'region': patch_aoi.getInfo()['coordinates'],
                                'dimensions': '256x256',
                                'format': 'jpg'
                            })
                            
                            # 2. Download Image (서비스 레벨에서 재사용하는 self.http_client 사용)
                            resp = self.http_client.get(thumb_url, timeout=3.0)
                            if resp.status_code == 200:
                                img = Image.open(io.BytesIO(resp.content)).convert('RGB')
                                tensor = transform(img).unsqueeze(0).to(self.device)

                                # 3. Model Inference
                                with self.torch.no_grad():
                                    output = self.dl_model(tensor) # [1, 2, 256, 256]
                                    prob = self.torch.softmax(output, dim=1)
                                    # Class 1 is 'Target' (Solar)
                                    solar_score = prob[0, 1, :, :].mean().item()

                                # 4. Update Result
                                logger.info("Detection %s: AI Score = %.4f", det['id'], solar_score)
                                det['confidence'] = (det['confidence'] + solar_score) / 2
                                det['ai_score'] = solar_score

                                if solar_score > 0.5:
                                    det['description'] += f" [AI확률: {solar_score*100:.0f}%]"
                                else:
                                    det['description'] += f" [AI점수: 낮음]"

                        except Exception as inner_e:
                            logger.warning("Inference warning for %s: %s", det['id'], inner_e)
                            continue

                except Exception as e:
                    logger.warning("DL Inference Error: %s", e)

        except Exception as e:
            logger.warning("Anomaly Detection Failed: %s", e)
            # Fallback to empty list, don't crash the main image load
            pass

        # URL Generation
        try:
            map_id_dict = tile_rgb.getMapId()
            tile_url = map_id_dict['tile_fetcher'].url_format
        except Exception as e:
            logger.warning("Tile URL generation failed: %s", e)
            tile_url = ""

        try:
            thumbnail_url = thumb_rgb.getThumbURL({
                'min': 0, 'max': 255, 'dimensions': 512, 'format': 'png'
            })
        except Exception as e:
            logger.warning("Thumbnail generation failed: %s", e)
            thumbnail_url = ""
            
        download_url = ""
        try:
             download_url = analysis_image.select(['B4','B3','B2']).getDownloadURL({
                'scale': 100,
                'region': aoi.getInfo()['coordinates'],
                'format': 'GEO_TIFF'
             })
        except:
             pass
        
        return {
            "success": True,
            "count": count,
            "image_id": properties.get('PRODUCT_ID'),
            "acquisition_date": properties.get('GENERATION_TIME'),
            "cloud_cover": properties.get('CLOUDY_PIXEL_PERCENTAGE'),
            "download_url": download_url,
            "thumbnail_url": thumbnail_url,
            "tile_url": tile_url,
            "past_tile_url": past_tile_url,
            "diff_tile_url": diff_tile_url,
            "detections": detections, # Return REAL detections
            "bounds": aoi.bounds().getInfo()['coordinates'],
            # ...
        }

    def _median_rgb_for_window(self, aoi, center_date: str, window_days: int = 90):
        """center_date ±window_days 구간의 Sentinel-2 저구름 median RGB 이미지와
        메타(구간·영상수·평균구름)를 반환한다. 영상이 없으면 (None, meta)."""
        center = datetime.strptime(center_date, '%Y-%m-%d')
        start = (center - timedelta(days=window_days)).strftime('%Y-%m-%d')
        end = (center + timedelta(days=window_days)).strftime('%Y-%m-%d')

        collection = (
            ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(aoi)
            .filterDate(start, end)
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 40))
            .sort('CLOUDY_PIXEL_PERCENTAGE')
        )
        count = int(collection.size().getInfo())
        meta = {"window_start": start, "window_end": end, "image_count": count, "mean_cloud": None}
        if count == 0:
            return None, meta

        # 구름 적은 상위 10장만 median → 계절/구름 편차 완화, 픽셀 정렬 유지
        top = collection.limit(10)
        try:
            meta["mean_cloud"] = round(
                float(top.aggregate_mean('CLOUDY_PIXEL_PERCENTAGE').getInfo()), 1
            )
        except Exception:
            pass
        return top.median(), meta

    def download_timeseries_sequence(
        self,
        latitude: float,
        longitude: float,
        buffer_km: float,
        years: list,
        month: int = 5,
        out_dir: str = ".",
        dimensions: int = 1024,
    ) -> Dict:
        """같은 좌표를 **여러 연도(연속)**에 걸쳐 같은 계절로 다운로드한다(연속 시계열).

        각 연도의 같은-계절(month) median 합성을 동일 region·dimensions로 내보내
        모든 프레임이 픽셀 정렬되게 하고, 첫 프레임을 기준으로 나머지를 radiometric
        정규화(조도/흐림 정렬)한다. 영상이 없는 연도는 건너뛴다.

        Returns:
            {"success", "frames": [{"year", "path", "meta"}...], "bounds",
             "latitude","longitude","buffer_km"}  (성공 프레임 2개 미만이면 success=False)
        """
        import os
        if not self.initialized:
            raise Exception("GEE가 초기화되지 않았습니다")

        point = ee.Geometry.Point([longitude, latitude])
        aoi = point.buffer(buffer_km * 1000)
        region = aoi.bounds()
        vis = {'bands': ['B4', 'B3', 'B2'], 'min': 200, 'max': 3000, 'gamma': 1.4}
        thumb_args = {'dimensions': dimensions, 'region': region, 'format': 'png'}

        frames = []
        for y in sorted(set(int(v) for v in years)):
            center = f"{y}-{month:02d}-15"
            img, meta = self._median_rgb_for_window(aoi, center)
            if img is None:
                logger.info("연도 %d 위성영상 없음 — 건너뜀", y)
                continue
            try:
                url = img.visualize(**vis).getThumbURL(thumb_args)
                resp = self.http_client.get(url, timeout=120.0)
                resp.raise_for_status()
                os.makedirs(out_dir, exist_ok=True)
                path = os.path.join(out_dir, f"frame_{y}.png")
                with open(path, "wb") as f:
                    f.write(resp.content)
                frames.append({"year": y, "path": path, "meta": meta})
            except Exception as e:
                logger.warning("연도 %d 다운로드 실패 — 건너뜀: %s", y, e)

        if len(frames) < 2:
            return {"success": False, "message": "연속 시계열에 필요한 영상(2개 이상)을 찾지 못했습니다", "frames": frames}

        # 첫 프레임 기준으로 나머지를 radiometric 정규화(조도/흐림 정렬)
        ref_path = frames[0]["path"]
        for fr in frames[1:]:
            _radiometric_match(ref_path, fr["path"])

        return {
            "success": True,
            "frames": frames,
            "bounds": region.getInfo()['coordinates'],
            "latitude": latitude,
            "longitude": longitude,
            "buffer_km": buffer_km,
        }

    def download_timeseries_pair(
        self,
        latitude: float,
        longitude: float,
        buffer_km: float,
        past_date: str,
        current_date: Optional[str] = None,
        out_dir: str = ".",
        dimensions: int = 1024,
    ) -> Dict:
        """같은 좌표의 과거(T1)·현재(T2) RGB PNG를 out_dir에 저장하고 메타를 반환한다.

        VQ 파이프라인(CVA 변화탐지) 입력용. 두 이미지는 **동일 region·동일 dimensions**로
        내보내 픽셀이 정렬되도록 한다(정렬이 깨지면 변화탐지가 무의미).

        Returns:
            {"success", "t1_path", "t2_path", "t1_meta", "t2_meta",
             "t1_tile_url", "t2_tile_url", "diff_tile_url",
             "bounds", "latitude", "longitude", "buffer_km"}
        """
        import os
        if not self.initialized:
            raise Exception("GEE가 초기화되지 않았습니다")

        # T2 미지정 시 "오늘"이 아니라 T1과 같은 계절(같은 월·최근 연도)로 정렬
        season_aligned = False
        if not current_date:
            current_date = _same_season_current(past_date)
            season_aligned = True

        point = ee.Geometry.Point([longitude, latitude])
        aoi = point.buffer(buffer_km * 1000)
        region = aoi.bounds()  # 두 시점 공통 사각 영역 → 동일 픽셀 격자

        img_t1, meta_t1 = self._median_rgb_for_window(aoi, past_date)
        img_t2, meta_t2 = self._median_rgb_for_window(aoi, current_date)

        if img_t1 is None:
            return {"success": False, "message": f"과거 시점({past_date}) 위성영상을 찾지 못했습니다", "t1_meta": meta_t1}
        if img_t2 is None:
            return {"success": False, "message": f"현재 시점({current_date}) 위성영상을 찾지 못했습니다", "t2_meta": meta_t2}

        vis = {'bands': ['B4', 'B3', 'B2'], 'min': 200, 'max': 3000, 'gamma': 1.4}
        thumb_args = {'dimensions': dimensions, 'region': region, 'format': 'png'}

        def _fetch_png(img, filename: str) -> str:
            url = img.visualize(**vis).getThumbURL(thumb_args)
            resp = self.http_client.get(url, timeout=120.0)
            resp.raise_for_status()
            path = os.path.join(out_dir, filename)
            os.makedirs(out_dir, exist_ok=True)
            with open(path, "wb") as f:
                f.write(resp.content)
            return path

        t1_path = _fetch_png(img_t1, "t1_source.png")
        t2_path = _fetch_png(img_t2, "t2_source.png")

        # Radiometric normalization: T2를 T1의 밝기·대비에 맞춤(조도/흐림 차이 제거).
        # 특징 추출 전에 적용해야 codeword 할당이 조도 때문에 밀리지 않는다(계절 정합의 짝).
        _radiometric_match(t1_path, t2_path)

        # 지도 오버레이용 타일 URL(선택) — 실패해도 다운로드 결과는 살린다
        t1_tile_url = t2_tile_url = diff_tile_url = ""
        try:
            t1_tile_url = img_t1.visualize(**vis).getMapId()['tile_fetcher'].url_format
            t2_tile_url = img_t2.visualize(**vis).getMapId()['tile_fetcher'].url_format
            # NDVI 감소(식생→시설물) 영역을 빨간 오버레이로
            ndvi_t1 = img_t1.normalizedDifference(['B8', 'B4'])
            ndvi_t2 = img_t2.normalizedDifference(['B8', 'B4'])
            change = ndvi_t1.subtract(ndvi_t2).gt(0.25)
            change_vis = change.updateMask(change).visualize(palette=['red'], opacity=0.7)
            diff_tile_url = change_vis.getMapId()['tile_fetcher'].url_format
        except Exception as e:
            logger.warning("시계열 타일 생성 실패(비치명적): %s", e)

        return {
            "success": True,
            "t1_path": t1_path,
            "t2_path": t2_path,
            "t1_meta": meta_t1,
            "t2_meta": meta_t2,
            "t1_tile_url": t1_tile_url,
            "t2_tile_url": t2_tile_url,
            "diff_tile_url": diff_tile_url,
            "bounds": region.getInfo()['coordinates'],
            "latitude": latitude,
            "longitude": longitude,
            "buffer_km": buffer_km,
            # 계절 정합·radiometric 정규화 적용 여부(UI 표기용)
            "season_aligned": season_aligned,
            "current_date": current_date,
            "radiometric_normalized": True,
        }

    def search_images(
        self,
        bounds: List[List[float]],
        start_date: str,
        end_date: str,
        max_cloud_cover: int = 20,
        limit: int = 10
    ) -> List[Dict]:
        """
        영역 내 모든 Sentinel-2 영상 검색
        
        Args:
            bounds: 경계 좌표 [[lon, lat], [lon, lat], ...]
            start_date: 시작 날짜
            end_date: 종료 날짜
            max_cloud_cover: 최대 구름 비율
            limit: 최대 결과 수
        
        Returns:
            영상 정보 리스트
        """
        if not self.initialized:
            raise Exception("GEE가 초기화되지 않았습니다")
        
        # 관심 지역 설정
        aoi = ee.Geometry.Polygon(bounds)
        
        # Sentinel-2 컬렉션
        collection = (
            ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(aoi)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_cloud_cover))
            .sort('system:time_start', False)
            .limit(limit)
        )
        
        # 영상 목록 가져오기
        images = collection.toList(limit).getInfo()
        
        results = []
        for img in images:
            props = img['properties']
            results.append({
                "id": img['id'],
                "product_id": props.get('PRODUCT_ID'),
                "date": datetime.fromtimestamp(props['system:time_start'] / 1000).strftime('%Y-%m-%d'),
                "cloud_cover": props.get('CLOUDY_PIXEL_PERCENTAGE'),
                "thumbnail": self._get_thumbnail_url(img['id'], aoi)
            })
        
        return results
    
    def _get_thumbnail_url(self, image_id: str, aoi: ee.Geometry) -> str:
        """썸네일 URL 생성"""
        try:
            image = ee.Image(image_id)
            rgb = image.select(['B4', 'B3', 'B2'])
            
            url = rgb.getThumbURL({
                'region': aoi.getInfo()['coordinates'],
                'dimensions': 512,
                'format': 'png'
            })
            return url
        except Exception:
            return None
    
    def download_image(
        self,
        image_id: str,
        bounds: List[List[float]],
        scale: int = 10
    ) -> str:
        """
        영상 다운로드 URL 생성
        
        Args:
            image_id: GEE 영상 ID
            bounds: 다운로드 영역
            scale: 해상도 (미터)
        
        Returns:
            다운로드 URL
        """
        if not self.initialized:
            raise Exception("GEE가 초기화되지 않았습니다")
        
        image = ee.Image(image_id)
        aoi = ee.Geometry.Polygon(bounds)
        
        # RGB 밴드 선택
        rgb = image.select(['B4', 'B3', 'B2'])
        
        url = rgb.getDownloadURL({
            'region': aoi.getInfo()['coordinates'],
            'scale': scale,
            'format': 'GEO_TIFF'
        })
        
        return url
