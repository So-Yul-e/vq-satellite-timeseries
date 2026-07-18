"""태양광 패널 탐지 모델 (SimpleSolarDetector + AdvancedSolarDetector)"""
import numpy as np
from typing import List, Dict, Tuple, Optional
import cv2

# Advanced detector import (PyTorch 필요)
try:
    from .advanced_solar_detector import AdvancedSolarDetector
    ADVANCED_AVAILABLE = True
except ImportError:
    ADVANCED_AVAILABLE = False
    print("Warning: Advanced solar detector (U-Net++) not available. Install PyTorch to use it.")


class SimpleSolarDetector:
    """
    간단한 태양광 패널 탐지기
    실제로는 U-Net++ 같은 딥러닝 모델을 사용하지만,
    2일 안에 완성하기 위해 간단한 이미지 처리 기반으로 구현
    """
    
    def __init__(self):
        self.min_area = 100  # 최소 패널 면적 (픽셀)
        self.max_area = 10000  # 최대 패널 면적
    
    def detect(self, image_path: str) -> List[Dict]:
        """
        이미지에서 태양광 패널 탐지
        
        Args:
            image_path: 이미지 파일 경로
            
        Returns:
            탐지된 패널 정보 리스트
        """
        # 이미지 로드
        img = cv2.imread(image_path)
        if img is None:
            return []
        
        # 그레이스케일 변환
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 밝은 영역 탐지 (태양광 패널은 반사율이 높음)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        
        # 노이즈 제거
        kernel = np.ones((5, 5), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        
        # 윤곽선 찾기
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        panels = []
        for i, contour in enumerate(contours):
            area = cv2.contourArea(contour)
            
            # 면적 필터링
            if self.min_area < area < self.max_area:
                # 바운딩 박스
                x, y, w, h = cv2.boundingRect(contour)
                
                # 직사각형 비율 확인 (태양광 패널은 대체로 직사각형)
                aspect_ratio = float(w) / h if h > 0 else 0
                
                if 0.5 < aspect_ratio < 3.0:  # 합리적인 비율
                    # 중심점 계산
                    M = cv2.moments(contour)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                    else:
                        cx, cy = x + w // 2, y + h // 2
                    
                    panels.append({
                        "id": f"panel_{i}",
                        "bbox": [int(x), int(y), int(w), int(h)],
                        "center": [int(cx), int(cy)],
                        "area": float(area),
                        "confidence": min(0.95, 0.6 + (area / self.max_area) * 0.3),
                        "status": "detected"
                    })
        
        return panels
    
    def detect_with_coordinates(
        self,
        image_path: str,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float
    ) -> List[Dict]:
        """
        이미지에서 패널 탐지 + 실제 좌표 변환
        
        Args:
            image_path: 이미지 경로
            lat_min, lat_max: 위도 범위
            lon_min, lon_max: 경도 범위
            
        Returns:
            실제 좌표가 포함된 패널 정보
        """
        panels = self.detect(image_path)
        
        if not panels:
            return []
        
        # 이미지 크기
        img = cv2.imread(image_path)
        height, width = img.shape[:2]
        
        # 픽셀 -> 실제 좌표 변환
        for panel in panels:
            cx, cy = panel["center"]
            
            # 정규화된 좌표 (0~1)
            norm_x = cx / width
            norm_y = cy / height
            
            # 실제 좌표 계산
            longitude = lon_min + (lon_max - lon_min) * norm_x
            latitude = lat_max - (lat_max - lat_min) * norm_y  # Y축은 반대
            
            panel["latitude"] = latitude
            panel["longitude"] = longitude
        
        return panels


class MockSolarDetector:
    """
    테스트용 Mock 탐지기
    실제 이미지 없이도 결과 생성
    """
    
    def detect_mock(self, latitude: float, longitude: float, count: int = 5) -> List[Dict]:
        """
        Mock 데이터 생성
        
        Args:
            latitude: 중심 위도
            longitude: 중심 경도
            count: 생성할 패널 개수
            
        Returns:
            가짜 패널 데이터
        """
        panels = []
        
        for i in range(count):
            # 중심점 주변에 랜덤 분포
            offset_lat = (np.random.random() - 0.5) * 0.01
            offset_lon = (np.random.random() - 0.5) * 0.01
            
            panels.append({
                "id": f"panel_{i+1}",
                "latitude": latitude + offset_lat,
                "longitude": longitude + offset_lon,
                "area": np.random.uniform(50, 200),
                "confidence": np.random.uniform(0.7, 0.95),
                "status": "detected",
                "permit_status": "unknown"  # 허가 상태 (나중에 DB 연동)
            })
        
        return panels
