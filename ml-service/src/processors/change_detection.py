"""시계열 변화 탐지 모듈"""
import numpy as np
from typing import Dict, Tuple, List, Optional
from scipy.spatial.distance import cdist
from scipy.ndimage import gaussian_filter
import pickle


class ChangeDetector:
    """VQ 기반 변화 탐지기"""

    def __init__(
        self,
        threshold_method: str = "otsu",
        spatial_smoothing: bool = True,
        smoothing_sigma: float = 1.0
    ):
        """
        Args:
            threshold_method: 'otsu', 'adaptive', 'manual' 중 하나
            spatial_smoothing: 공간적 스무딩 적용 여부
            smoothing_sigma: 가우시안 필터 시그마 값
        """
        self.threshold_method = threshold_method
        self.spatial_smoothing = spatial_smoothing
        self.smoothing_sigma = smoothing_sigma

    def detect_changes(
        self,
        features_t1: np.ndarray,
        features_t2: np.ndarray,
        codebook_t1: Optional[np.ndarray] = None,
        codebook_t2: Optional[np.ndarray] = None,
        image_shape: Optional[Tuple[int, int]] = None,
        manual_threshold: Optional[float] = None
    ) -> Dict:
        """
        두 시점의 특징 벡터를 비교하여 변화 탐지

        Args:
            features_t1: 시점 1의 특징 벡터 (N, D)
            features_t2: 시점 2의 특징 벡터 (N, D)
            codebook_t1: 시점 1의 코드북 (옵션)
            codebook_t2: 시점 2의 코드북 (옵션)
            image_shape: 원본 이미지 크기 (H, W) - 변화 맵 생성용
            manual_threshold: 수동 임계값 (threshold_method='manual'일 때)

        Returns:
            변화 탐지 결과 딕셔너리
        """
        print(f"Detecting changes between two time points...")
        print(f"t1 features: {features_t1.shape}, t2 features: {features_t2.shape}")

        # 1. Change Vector Analysis (CVA)
        change_vectors, change_magnitudes = self._calculate_change_vectors(
            features_t1, features_t2
        )

        # 2. 코드북 기반 변화 분석 (있는 경우)
        if codebook_t1 is not None and codebook_t2 is not None:
            codebook_distances = self._calculate_codebook_distances(
                codebook_t1, codebook_t2
            )
        else:
            codebook_distances = None

        # 3. 임계값 계산
        if manual_threshold is not None:
            threshold = manual_threshold
        else:
            threshold = self._calculate_threshold(change_magnitudes)

        # 4. 변화 맵 생성
        change_mask = change_magnitudes > threshold

        # 5. 공간적 스무딩 (옵션)
        if self.spatial_smoothing and image_shape is not None:
            change_mask = self._apply_spatial_smoothing(
                change_mask, image_shape
            )

        # 6. 변화 통계 계산
        stats = self._calculate_change_statistics(
            change_magnitudes, change_mask, threshold
        )

        # 7. 변화 유형 분류
        change_types = self._classify_change_types(
            change_vectors, change_mask
        )

        result = {
            "change_magnitudes": change_magnitudes,
            "change_mask": change_mask,
            "threshold": float(threshold),
            "statistics": stats,
            "change_types": change_types
        }

        if codebook_distances is not None:
            result["codebook_distances"] = codebook_distances

        print(f"Changes detected: {stats['n_changed']} / {len(change_mask)} pixels")
        print(f"Change percentage: {stats['change_percentage']:.2f}%")

        return result

    def _calculate_change_vectors(
        self,
        features_t1: np.ndarray,
        features_t2: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Change Vector Analysis (CVA)"""
        # 특징 벡터 개수가 다르면 최소 개수로 맞춤
        min_len = min(len(features_t1), len(features_t2))
        features_t1 = features_t1[:min_len]
        features_t2 = features_t2[:min_len]

        # 변화 벡터: Δv = v_t2 - v_t1
        change_vectors = features_t2 - features_t1

        # 변화 크기: ||Δv||
        change_magnitudes = np.linalg.norm(change_vectors, axis=1)

        return change_vectors, change_magnitudes

    def _calculate_codebook_distances(
        self,
        codebook_t1: np.ndarray,
        codebook_t2: np.ndarray
    ) -> Dict:
        """코드북 간 거리 계산"""
        # 코드북 중심점 간 거리 행렬
        distance_matrix = cdist(codebook_t1, codebook_t2, metric='euclidean')

        # 각 t1 코드에 대한 가장 가까운 t2 코드
        min_distances = distance_matrix.min(axis=1)
        closest_codes = distance_matrix.argmin(axis=1)

        return {
            "distance_matrix": distance_matrix,
            "min_distances": min_distances,
            "closest_codes": closest_codes,
            "avg_distance": float(np.mean(min_distances)),
            "max_distance": float(np.max(min_distances))
        }

    def _calculate_threshold(self, magnitudes: np.ndarray) -> float:
        """변화 임계값 계산"""
        if self.threshold_method == "otsu":
            # Otsu's method
            threshold = self._otsu_threshold(magnitudes)
        elif self.threshold_method == "adaptive":
            # 평균 + k*표준편차
            threshold = np.mean(magnitudes) + 2 * np.std(magnitudes)
        else:
            raise ValueError(f"Unknown threshold method: {self.threshold_method}")

        return float(threshold)

    def _otsu_threshold(self, values: np.ndarray) -> float:
        """Otsu's method로 최적 임계값 찾기"""
        # 히스토그램 생성
        hist, bin_edges = np.histogram(values, bins=256)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

        # 클래스 확률과 평균 계산
        weight1 = np.cumsum(hist)
        weight2 = np.cumsum(hist[::-1])[::-1]

        # 평균 계산
        mean1 = np.cumsum(hist * bin_centers) / weight1
        mean2 = (np.cumsum((hist * bin_centers)[::-1]) / weight2[::-1])[::-1]

        # 클래스 간 분산 계산
        variance = weight1[:-1] * weight2[1:] * (mean1[:-1] - mean2[1:]) ** 2

        # 최대 분산을 갖는 임계값 선택
        idx = np.argmax(variance)
        threshold = bin_centers[idx]

        return threshold

    def _apply_spatial_smoothing(
        self,
        change_mask: np.ndarray,
        image_shape: Tuple[int, int]
    ) -> np.ndarray:
        """공간적 스무딩 적용 (노이즈 제거)"""
        # 1D 마스크를 2D로 reshape
        try:
            # 패치 기반인 경우 근사적으로 reshape
            n_patches = len(change_mask)
            grid_size = int(np.sqrt(n_patches))

            if grid_size * grid_size == n_patches:
                mask_2d = change_mask.reshape(grid_size, grid_size)
            else:
                # 맞지 않으면 그냥 반환
                return change_mask

            # 가우시안 필터 적용
            smoothed = gaussian_filter(
                mask_2d.astype(float),
                sigma=self.smoothing_sigma
            )

            # 다시 이진화
            smoothed_mask = (smoothed > 0.5).flatten()

            return smoothed_mask

        except:
            return change_mask

    def _calculate_change_statistics(
        self,
        magnitudes: np.ndarray,
        change_mask: np.ndarray,
        threshold: float
    ) -> Dict:
        """변화 통계 계산"""
        n_total = len(change_mask)
        n_changed = int(np.sum(change_mask))
        n_unchanged = n_total - n_changed

        changed_magnitudes = magnitudes[change_mask]
        unchanged_magnitudes = magnitudes[~change_mask]

        stats = {
            "n_total": n_total,
            "n_changed": n_changed,
            "n_unchanged": n_unchanged,
            "change_percentage": float(n_changed / n_total * 100),
            "threshold": float(threshold),
            "magnitude_mean": float(np.mean(magnitudes)),
            "magnitude_std": float(np.std(magnitudes)),
            "magnitude_max": float(np.max(magnitudes)),
            "magnitude_min": float(np.min(magnitudes))
        }

        if n_changed > 0:
            stats["changed_magnitude_mean"] = float(np.mean(changed_magnitudes))
            stats["changed_magnitude_std"] = float(np.std(changed_magnitudes))
        else:
            stats["changed_magnitude_mean"] = 0.0
            stats["changed_magnitude_std"] = 0.0

        if n_unchanged > 0:
            stats["unchanged_magnitude_mean"] = float(np.mean(unchanged_magnitudes))
            stats["unchanged_magnitude_std"] = float(np.std(unchanged_magnitudes))
        else:
            stats["unchanged_magnitude_mean"] = 0.0
            stats["unchanged_magnitude_std"] = 0.0

        return stats

    def _classify_change_types(
        self,
        change_vectors: np.ndarray,
        change_mask: np.ndarray
    ) -> Dict:
        """변화 유형 분류 (방향 기반)"""
        if np.sum(change_mask) == 0:
            return {
                "types": [],
                "counts": {}
            }

        # 변화가 있는 벡터만 추출
        changed_vectors = change_vectors[change_mask]

        # PCA로 주요 방향 찾기 (간단한 버전: 평균 방향)
        mean_direction = np.mean(changed_vectors, axis=0)
        mean_direction_norm = mean_direction / (np.linalg.norm(mean_direction) + 1e-10)

        # 각 변화 벡터와 평균 방향의 내적으로 유사도 계산
        similarities = np.dot(changed_vectors, mean_direction_norm)

        # 유사한 변화 / 다른 변화로 분류
        similar_changes = np.sum(similarities > 0.7)
        different_changes = len(similarities) - similar_changes

        return {
            "mean_direction": mean_direction.tolist(),
            "similar_changes": int(similar_changes),
            "different_changes": int(different_changes),
            "similarity_mean": float(np.mean(similarities)),
            "similarity_std": float(np.std(similarities))
        }

    def detect_change_regions(
        self,
        change_mask: np.ndarray,
        image_shape: Tuple[int, int],
        min_area: int = 10
    ) -> List[Dict]:
        """변화 영역 검출 (연결 성분 분석)"""
        from scipy.ndimage import label

        # 2D로 변환
        try:
            n_patches = len(change_mask)
            grid_size = int(np.sqrt(n_patches))

            if grid_size * grid_size != n_patches:
                return []

            mask_2d = change_mask.reshape(grid_size, grid_size)

            # 연결 성분 레이블링
            labeled, n_regions = label(mask_2d)

            regions = []
            for region_id in range(1, n_regions + 1):
                region_mask = labeled == region_id
                area = np.sum(region_mask)

                if area >= min_area:
                    # 바운딩 박스
                    rows, cols = np.where(region_mask)
                    bbox = {
                        "x_min": int(cols.min()),
                        "y_min": int(rows.min()),
                        "x_max": int(cols.max()),
                        "y_max": int(rows.max())
                    }

                    # 중심점
                    center = {
                        "x": int(np.mean(cols)),
                        "y": int(np.mean(rows))
                    }

                    regions.append({
                        "region_id": region_id,
                        "area": int(area),
                        "bbox": bbox,
                        "center": center
                    })

            print(f"Detected {len(regions)} change regions")
            return regions

        except Exception as e:
            print(f"Error in region detection: {e}")
            return []

    def save_results(self, results: Dict, file_path: str):
        """결과 저장"""
        with open(file_path, 'wb') as f:
            pickle.dump(results, f)
        print(f"Results saved to {file_path}")

    def load_results(self, file_path: str) -> Dict:
        """결과 로드"""
        with open(file_path, 'rb') as f:
            results = pickle.load(f)
        print(f"Results loaded from {file_path}")
        return results
