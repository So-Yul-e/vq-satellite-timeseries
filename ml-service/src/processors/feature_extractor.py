import torch
import torch.nn as nn
import numpy as np
from PIL import Image
from typing import List, Tuple, Optional
from pathlib import Path
import torchvision.models as models
from torchvision import transforms


class FeatureExtractor:
    """CNN 기반 특징 추출기 (ResNet50)"""

    def __init__(self, model_path: Optional[str] = None, device: str = "cpu"):
        """
        Args:
            model_path: 사전 학습된 모델 경로 (None이면 ImageNet 사전학습 모델 사용)
            device: 'cpu' 또는 'cuda'
        """
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        self.model = self._load_model(model_path)
        self.patch_size = 224  # ResNet 입력 크기
        self.stride = 112  # 50% 오버랩

        # ImageNet 정규화
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])

        print(f"FeatureExtractor initialized on {self.device}")

    def _load_model(self, model_path: Optional[str] = None) -> nn.Module:
        """사전 학습된 ResNet50 모델 로드"""
        # ResNet50을 특징 추출기로 사용
        model = models.resnet50(pretrained=True)

        # 마지막 FC 레이어 제거 (특징 벡터만 추출)
        model = nn.Sequential(*list(model.children())[:-1])
        model.eval()

        if model_path and Path(model_path).exists():
            model.load_state_dict(torch.load(model_path, map_location=self.device))
            print(f"Custom model loaded from {model_path}")

        model.to(self.device)
        return model

    def extract(self, image_path: str) -> np.ndarray:
        """
        위성 영상에서 특징 벡터 추출

        Args:
            image_path: 이미지 파일 경로

        Returns:
            특징 벡터 배열 (N, 2048) - N은 패치 개수, 2048은 ResNet50 특징 차원
        """
        # 영상 로드
        image_data = self._load_image(image_path)

        # Patch 추출
        patches = self._extract_patches(image_data)

        if len(patches) == 0:
            print(f"Warning: No patches extracted from {image_path}")
            return np.array([])

        # 특징 추출
        features = []
        batch_size = 32  # 배치로 처리하여 속도 향상

        with torch.no_grad():
            for i in range(0, len(patches), batch_size):
                batch_patches = patches[i:i+batch_size]

                # 패치를 텐서로 변환
                batch_tensors = []
                for patch in batch_patches:
                    patch_tensor = self._preprocess_patch(patch)
                    batch_tensors.append(patch_tensor)

                # 배치로 합치기
                batch = torch.cat(batch_tensors, dim=0).to(self.device)

                # 특징 추출
                batch_features = self.model(batch)
                batch_features = batch_features.squeeze(-1).squeeze(-1)  # (B, 2048, 1, 1) -> (B, 2048)

                features.append(batch_features.cpu().numpy())

        # 모든 특징 벡터 합치기
        features = np.vstack(features)

        print(f"Extracted {len(features)} feature vectors from {image_path}")
        return features

    def _load_image(self, image_path: str) -> np.ndarray:
        """이미지 로드 (GeoTIFF 또는 일반 이미지)"""
        try:
            # GeoTIFF인 경우
            import rasterio
            with rasterio.open(image_path) as src:
                # RGB 밴드만 사용 (또는 첫 3개 밴드)
                if src.count >= 3:
                    data = src.read([1, 2, 3])
                else:
                    data = src.read(1)
                    data = np.stack([data, data, data])

                # (C, H, W) -> (H, W, C)
                data = np.transpose(data, (1, 2, 0))

                # 정규화 (0-255 범위로)
                if data.max() > 255:
                    data = (data / data.max() * 255).astype(np.uint8)

        except Exception as e:
            # 일반 이미지인 경우 PIL 사용
            try:
                with Image.open(image_path) as img:
                    data = np.array(img.convert("RGB"))
            except Exception as e2:
                raise ValueError(f"Failed to load image {image_path}: {e2}")

        return data

    def _extract_patches(self, image: np.ndarray) -> List[np.ndarray]:
        """이미지에서 패치 추출 (슬라이딩 윈도우)"""
        patches = []
        h, w = image.shape[:2]

        # 이미지가 너무 작으면 리사이즈
        if h < self.patch_size or w < self.patch_size:
            print(f"Warning: Image too small ({h}x{w}), resizing to {self.patch_size}x{self.patch_size}")
            image = np.array(Image.fromarray(image).resize((self.patch_size, self.patch_size)))
            h, w = image.shape[:2]

        for y in range(0, h - self.patch_size + 1, self.stride):
            for x in range(0, w - self.patch_size + 1, self.stride):
                patch = image[y:y+self.patch_size, x:x+self.patch_size]
                patches.append(patch)

        return patches

    def _preprocess_patch(self, patch: np.ndarray) -> torch.Tensor:
        """패치 전처리 및 정규화"""
        # uint8로 변환
        if patch.dtype != np.uint8:
            patch = (patch * 255).astype(np.uint8)

        # PIL Image로 변환
        img = Image.fromarray(patch)

        # Transform 적용
        tensor = self.transform(img)
        return tensor.unsqueeze(0)  # 배치 차원 추가

    def extract_single_patch(self, image_path: str) -> np.ndarray:
        """단일 이미지를 하나의 패치로 처리 (작은 이미지용)"""
        image_data = self._load_image(image_path)

        with torch.no_grad():
            patch_tensor = self._preprocess_patch(image_data)
            patch_tensor = patch_tensor.to(self.device)

            feature = self.model(patch_tensor)
            feature = feature.squeeze().cpu().numpy()

        return feature
