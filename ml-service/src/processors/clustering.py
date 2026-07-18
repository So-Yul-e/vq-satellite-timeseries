"""클러스터링 프로세서 모듈"""
import numpy as np
from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
from sklearn.metrics import silhouette_score, davies_bouldin_score, calinski_harabasz_score
from typing import Dict, List, Tuple, Optional
import pickle


class ClusteringProcessor:
    """클러스터링 처리기"""

    def __init__(self, algorithm: str = "kmeans"):
        """
        Args:
            algorithm: 'kmeans', 'dbscan', 'hierarchical' 중 하나
        """
        self.algorithm = algorithm
        self.model = None
        self.labels = None
        self.centers = None

    def cluster(
        self,
        feature_vectors: np.ndarray,
        n_clusters: int = 8,
        **kwargs
    ) -> Dict:
        """
        특징 벡터 클러스터링

        Args:
            feature_vectors: 특징 벡터 배열 (N, D)
            n_clusters: 클러스터 개수 (kmeans, hierarchical용)
            **kwargs: 알고리즘별 추가 파라미터

        Returns:
            클러스터링 결과 딕셔너리
        """
        print(f"Clustering with {self.algorithm}...")
        print(f"Input shape: {feature_vectors.shape}")

        if self.algorithm == "kmeans":
            return self._kmeans_clustering(feature_vectors, n_clusters, **kwargs)
        elif self.algorithm == "dbscan":
            return self._dbscan_clustering(feature_vectors, **kwargs)
        elif self.algorithm == "hierarchical":
            return self._hierarchical_clustering(feature_vectors, n_clusters, **kwargs)
        else:
            raise ValueError(f"지원하지 않는 알고리즘: {self.algorithm}")

    def _kmeans_clustering(
        self,
        vectors: np.ndarray,
        n_clusters: int,
        random_state: int = 42
    ) -> Dict:
        """K-means 클러스터링"""
        self.model = KMeans(
            n_clusters=n_clusters,
            random_state=random_state,
            n_init=10,
            max_iter=300
        )

        self.labels = self.model.fit_predict(vectors)
        self.centers = self.model.cluster_centers_

        # 클러스터 통계 계산
        stats = self._calculate_cluster_stats(vectors, self.labels, self.centers)

        result = {
            "labels": self.labels,
            "centers": self.centers,
            "n_clusters": n_clusters,
            "inertia": float(self.model.inertia_),
            "statistics": stats
        }

        # 평가 메트릭
        metrics = self._calculate_metrics(vectors, self.labels)
        result.update(metrics)

        print(f"K-means completed: {n_clusters} clusters, inertia={result['inertia']:.2f}")

        return result

    def _dbscan_clustering(
        self,
        vectors: np.ndarray,
        eps: float = 0.5,
        min_samples: int = 5
    ) -> Dict:
        """DBSCAN 클러스터링 (밀도 기반)"""
        self.model = DBSCAN(eps=eps, min_samples=min_samples)
        self.labels = self.model.fit_predict(vectors)

        n_clusters = len(set(self.labels)) - (1 if -1 in self.labels else 0)
        n_noise = int(np.sum(self.labels == -1))

        # DBSCAN은 중심점이 없으므로 계산
        self.centers = self._calculate_dbscan_centers(vectors, self.labels)

        stats = self._calculate_cluster_stats(vectors, self.labels, self.centers)

        result = {
            "labels": self.labels,
            "centers": self.centers,
            "n_clusters": n_clusters,
            "n_noise": n_noise,
            "statistics": stats
        }

        # 평가 메트릭 (노이즈 제외)
        if n_clusters > 1:
            valid_mask = self.labels != -1
            valid_vectors = vectors[valid_mask]
            valid_labels = self.labels[valid_mask]
            metrics = self._calculate_metrics(valid_vectors, valid_labels)
            result.update(metrics)

        print(f"DBSCAN completed: {n_clusters} clusters, {n_noise} noise points")

        return result

    def _hierarchical_clustering(
        self,
        vectors: np.ndarray,
        n_clusters: int,
        linkage: str = 'ward'
    ) -> Dict:
        """계층적 클러스터링"""
        self.model = AgglomerativeClustering(
            n_clusters=n_clusters,
            linkage=linkage
        )

        self.labels = self.model.fit_predict(vectors)

        # 중심점 계산
        self.centers = np.array([
            vectors[self.labels == i].mean(axis=0)
            for i in range(n_clusters)
        ])

        stats = self._calculate_cluster_stats(vectors, self.labels, self.centers)

        result = {
            "labels": self.labels,
            "centers": self.centers,
            "n_clusters": n_clusters,
            "statistics": stats
        }

        # 평가 메트릭
        metrics = self._calculate_metrics(vectors, self.labels)
        result.update(metrics)

        print(f"Hierarchical clustering completed: {n_clusters} clusters")

        return result

    def _calculate_cluster_stats(
        self,
        vectors: np.ndarray,
        labels: np.ndarray,
        centers: np.ndarray
    ) -> List[Dict]:
        """클러스터 통계 계산"""
        stats = []

        unique_labels = np.unique(labels)
        for label in unique_labels:
            if label == -1:  # 노이즈 (DBSCAN)
                continue

            cluster_vectors = vectors[labels == label]
            cluster_size = len(cluster_vectors)

            # 중심점까지의 평균 거리
            if label < len(centers):
                distances = np.linalg.norm(
                    cluster_vectors - centers[label],
                    axis=1
                )
                avg_distance = float(np.mean(distances))
                std_distance = float(np.std(distances))
            else:
                avg_distance = 0.0
                std_distance = 0.0

            stats.append({
                "label": int(label),
                "size": int(cluster_size),
                "percentage": float(cluster_size / len(labels) * 100),
                "center": centers[label].tolist() if label < len(centers) else [],
                "avg_distance": avg_distance,
                "std_distance": std_distance
            })

        return stats

    def _calculate_dbscan_centers(
        self,
        vectors: np.ndarray,
        labels: np.ndarray
    ) -> np.ndarray:
        """DBSCAN 클러스터 중심점 계산"""
        unique_labels = np.unique(labels)
        centers = []

        for label in unique_labels:
            if label == -1:  # 노이즈
                continue

            cluster_vectors = vectors[labels == label]
            center = np.mean(cluster_vectors, axis=0)
            centers.append(center)

        return np.array(centers) if centers else np.array([])

    def _calculate_metrics(
        self,
        vectors: np.ndarray,
        labels: np.ndarray
    ) -> Dict:
        """클러스터링 평가 메트릭 계산"""
        metrics = {}

        # 클러스터가 1개면 메트릭 계산 불가
        n_clusters = len(np.unique(labels))
        if n_clusters <= 1:
            return metrics

        # 샘플이 너무 많으면 샘플링
        if len(vectors) > 10000:
            sample_idx = np.random.choice(len(vectors), 10000, replace=False)
            sample_vectors = vectors[sample_idx]
            sample_labels = labels[sample_idx]
        else:
            sample_vectors = vectors
            sample_labels = labels

        try:
            # Silhouette Score
            metrics['silhouette_score'] = float(
                silhouette_score(sample_vectors, sample_labels)
            )
        except:
            metrics['silhouette_score'] = None

        try:
            # Davies-Bouldin Index
            metrics['davies_bouldin_score'] = float(
                davies_bouldin_score(sample_vectors, sample_labels)
            )
        except:
            metrics['davies_bouldin_score'] = None

        try:
            # Calinski-Harabasz Index
            metrics['calinski_harabasz_score'] = float(
                calinski_harabasz_score(sample_vectors, sample_labels)
            )
        except:
            metrics['calinski_harabasz_score'] = None

        return metrics

    def get_labels(self) -> np.ndarray:
        """클러스터 레이블 반환"""
        if self.labels is None:
            raise ValueError("클러스터링이 수행되지 않았습니다.")
        return self.labels

    def get_centers(self) -> np.ndarray:
        """클러스터 중심점 반환"""
        if self.centers is None:
            raise ValueError("클러스터링이 수행되지 않았습니다.")
        return self.centers

    def save_model(self, file_path: str):
        """모델 저장"""
        if self.model is None:
            raise ValueError("모델이 학습되지 않았습니다.")

        save_data = {
            'algorithm': self.algorithm,
            'model': self.model,
            'labels': self.labels,
            'centers': self.centers
        }

        with open(file_path, 'wb') as f:
            pickle.dump(save_data, f)

        print(f"Model saved to {file_path}")

    def load_model(self, file_path: str):
        """모델 로드"""
        with open(file_path, 'rb') as f:
            data = pickle.load(f)

        self.algorithm = data['algorithm']
        self.model = data['model']
        self.labels = data['labels']
        self.centers = data['centers']

        print(f"Model loaded from {file_path}")
