import numpy as np
from sklearn.cluster import KMeans, MiniBatchKMeans
from sklearn.metrics import silhouette_score, davies_bouldin_score, calinski_harabasz_score
from typing import Dict, Tuple, Optional
import pickle
from pathlib import Path


class VQCodebookGenerator:
    """VQ 코드북 생성기 (K-means 기반)"""

    def __init__(
        self,
        codebook_size: int = 256,
        random_state: int = 42,
        use_minibatch: bool = False,
        batch_size: int = 1000
    ):
        """
        Args:
            codebook_size: 코드북 크기 (클러스터 개수)
            random_state: 난수 시드
            use_minibatch: Mini-Batch K-means 사용 여부 (대용량 데이터용)
            batch_size: Mini-Batch 크기
        """
        self.codebook_size = codebook_size
        self.random_state = random_state
        self.use_minibatch = use_minibatch
        self.batch_size = batch_size
        self.kmeans = None
        self.codebook = None
        self.metrics = {}

    def generate(self, feature_vectors: np.ndarray) -> np.ndarray:
        """
        특징 벡터로부터 VQ 코드북 생성

        Args:
            feature_vectors: 특징 벡터 배열 (N, D)

        Returns:
            코드북 (K, D) - K는 코드북 크기, D는 특징 차원
        """
        print(f"Generating VQ codebook with size {self.codebook_size}...")
        print(f"Input shape: {feature_vectors.shape}")

        # K-means 클러스터링
        if self.use_minibatch:
            print(f"Using Mini-Batch K-means (batch_size={self.batch_size})")
            self.kmeans = MiniBatchKMeans(
                n_clusters=self.codebook_size,
                random_state=self.random_state,
                batch_size=self.batch_size,
                max_iter=300,
                n_init=10
            )
        else:
            print("Using standard K-means")
            self.kmeans = KMeans(
                n_clusters=self.codebook_size,
                random_state=self.random_state,
                n_init=10,
                max_iter=300
            )

        self.kmeans.fit(feature_vectors)

        # 코드북은 클러스터 중심점들
        self.codebook = self.kmeans.cluster_centers_

        # 평가 메트릭 계산
        self._calculate_metrics(feature_vectors)

        print(f"Codebook generated: {self.codebook.shape}")
        print(f"Inertia: {self.metrics.get('inertia', 0):.2f}")

        return self.codebook

    def quantize(self, feature_vectors: np.ndarray) -> np.ndarray:
        """
        특징 벡터를 코드북을 사용하여 양자화

        Args:
            feature_vectors: 특징 벡터 배열 (N, D)

        Returns:
            코드북 인덱스 배열 (N,)
        """
        if self.kmeans is None:
            raise ValueError("코드북이 생성되지 않았습니다. generate()를 먼저 호출하세요.")

        # 각 벡터에 가장 가까운 코드북 인덱스 찾기
        indices = self.kmeans.predict(feature_vectors)

        return indices

    def get_codebook(self) -> np.ndarray:
        """생성된 코드북 반환"""
        if self.codebook is None:
            raise ValueError("코드북이 생성되지 않았습니다.")
        return self.codebook

    def get_metrics(self) -> Dict:
        """평가 메트릭 반환"""
        return self.metrics

    def _calculate_metrics(self, feature_vectors: np.ndarray):
        """클러스터링 품질 평가 메트릭 계산"""
        labels = self.kmeans.predict(feature_vectors)

        # Inertia (클러스터 내 분산)
        self.metrics['inertia'] = float(self.kmeans.inertia_)

        # 샘플이 너무 많으면 샘플링하여 계산 (속도 향상)
        if len(feature_vectors) > 10000:
            sample_idx = np.random.choice(len(feature_vectors), 10000, replace=False)
            sample_vectors = feature_vectors[sample_idx]
            sample_labels = labels[sample_idx]
        else:
            sample_vectors = feature_vectors
            sample_labels = labels

        try:
            # Silhouette Score (클러스터 분리도)
            # -1 ~ 1, 높을수록 좋음
            self.metrics['silhouette_score'] = float(
                silhouette_score(sample_vectors, sample_labels)
            )
        except:
            self.metrics['silhouette_score'] = None

        try:
            # Davies-Bouldin Index (클러스터 분리도)
            # 0 이상, 낮을수록 좋음
            self.metrics['davies_bouldin_score'] = float(
                davies_bouldin_score(sample_vectors, sample_labels)
            )
        except:
            self.metrics['davies_bouldin_score'] = None

        try:
            # Calinski-Harabasz Index (클러스터 분산 비율)
            # 높을수록 좋음
            self.metrics['calinski_harabasz_score'] = float(
                calinski_harabasz_score(sample_vectors, sample_labels)
            )
        except:
            self.metrics['calinski_harabasz_score'] = None

        # 클러스터별 통계
        cluster_stats = []
        for i in range(self.codebook_size):
            cluster_size = np.sum(labels == i)
            cluster_stats.append({
                'cluster_id': int(i),
                'size': int(cluster_size),
                'percentage': float(cluster_size / len(labels) * 100)
            })

        self.metrics['cluster_stats'] = cluster_stats

    def save_codebook(self, file_path: str):
        """코드북 저장"""
        if self.codebook is None:
            raise ValueError("코드북이 생성되지 않았습니다.")

        save_data = {
            'codebook': self.codebook,
            'kmeans': self.kmeans,
            'codebook_size': self.codebook_size,
            'metrics': self.metrics,
            'use_minibatch': self.use_minibatch
        }

        with open(file_path, 'wb') as f:
            pickle.dump(save_data, f)

        print(f"Codebook saved to {file_path}")

    def load_codebook(self, file_path: str):
        """코드북 로드"""
        if not Path(file_path).exists():
            raise FileNotFoundError(f"Codebook file not found: {file_path}")

        with open(file_path, 'rb') as f:
            data = pickle.load(f)

        self.codebook = data['codebook']
        self.kmeans = data['kmeans']
        self.codebook_size = data['codebook_size']
        self.metrics = data.get('metrics', {})
        self.use_minibatch = data.get('use_minibatch', False)

        print(f"Codebook loaded from {file_path}")
        print(f"Codebook shape: {self.codebook.shape}")

    def find_optimal_k(
        self,
        feature_vectors: np.ndarray,
        k_range: Tuple[int, int] = (2, 20),
        method: str = 'elbow'
    ) -> int:
        """
        최적의 클러스터 수 (K) 찾기

        Args:
            feature_vectors: 특징 벡터
            k_range: 탐색할 K 범위 (min, max)
            method: 'elbow' 또는 'silhouette'

        Returns:
            최적 K 값
        """
        print(f"Finding optimal K in range {k_range}...")

        k_min, k_max = k_range
        scores = []

        for k in range(k_min, k_max + 1):
            kmeans = KMeans(n_clusters=k, random_state=self.random_state, n_init=10)
            labels = kmeans.fit_predict(feature_vectors)

            if method == 'elbow':
                score = kmeans.inertia_
            elif method == 'silhouette':
                score = silhouette_score(feature_vectors, labels)
            else:
                raise ValueError(f"Unknown method: {method}")

            scores.append((k, score))
            print(f"K={k}: {method}={score:.2f}")

        # Elbow method: 가장 큰 기울기 변화점 찾기
        if method == 'elbow':
            # 2차 미분 근사
            diffs = np.diff([s for _, s in scores])
            optimal_k = k_min + np.argmax(np.abs(np.diff(diffs))) + 1
        else:
            # Silhouette: 최대값 찾기
            optimal_k = max(scores, key=lambda x: x[1])[0]

        print(f"Optimal K: {optimal_k}")
        return optimal_k
