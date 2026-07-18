"""평가 메트릭 모듈"""
import numpy as np
from typing import Dict, Optional, Tuple
from sklearn.metrics import (
    silhouette_score,
    davies_bouldin_score,
    calinski_harabasz_score,
    confusion_matrix,
    precision_score,
    recall_score,
    f1_score,
    accuracy_score
)
import json


class MetricsEvaluator:
    """VQ Clustering 및 변화 탐지 평가 메트릭"""

    def __init__(self):
        self.results = {}

    def evaluate_clustering(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        ground_truth: Optional[np.ndarray] = None
    ) -> Dict:
        """
        클러스터링 품질 평가

        Args:
            features: 특징 벡터 (N, D)
            labels: 클러스터 레이블 (N,)
            ground_truth: 실제 레이블 (있는 경우) (N,)

        Returns:
            평가 메트릭 딕셔너리
        """
        print("Evaluating clustering quality...")

        metrics = {}

        # 비지도 학습 메트릭
        unsupervised_metrics = self._unsupervised_clustering_metrics(
            features, labels
        )
        metrics.update(unsupervised_metrics)

        # 지도 학습 메트릭 (ground truth가 있는 경우)
        if ground_truth is not None:
            supervised_metrics = self._supervised_clustering_metrics(
                labels, ground_truth
            )
            metrics.update(supervised_metrics)

        self.results['clustering'] = metrics
        self._print_clustering_summary(metrics)

        return metrics

    def evaluate_change_detection(
        self,
        predicted_mask: np.ndarray,
        ground_truth: Optional[np.ndarray] = None,
        change_magnitudes: Optional[np.ndarray] = None
    ) -> Dict:
        """
        변화 탐지 평가

        Args:
            predicted_mask: 예측된 변화 마스크 (N,)
            ground_truth: 실제 변화 마스크 (있는 경우) (N,)
            change_magnitudes: 변화 크기 (N,)

        Returns:
            평가 메트릭 딕셔너리
        """
        print("Evaluating change detection...")

        metrics = {}

        # 기본 통계
        metrics['n_total'] = int(len(predicted_mask))
        metrics['n_changed'] = int(np.sum(predicted_mask))
        metrics['n_unchanged'] = int(np.sum(~predicted_mask))
        metrics['change_percentage'] = float(metrics['n_changed'] / metrics['n_total'] * 100)

        # 변화 크기 통계
        if change_magnitudes is not None:
            mag_stats = self._magnitude_statistics(
                change_magnitudes, predicted_mask
            )
            metrics.update(mag_stats)

        # 지도 학습 메트릭 (ground truth가 있는 경우)
        if ground_truth is not None:
            supervised_metrics = self._supervised_change_detection_metrics(
                predicted_mask, ground_truth
            )
            metrics.update(supervised_metrics)

        self.results['change_detection'] = metrics
        self._print_change_detection_summary(metrics)

        return metrics

    def evaluate_vq_codebook(
        self,
        codebook: np.ndarray,
        features: np.ndarray,
        labels: np.ndarray
    ) -> Dict:
        """
        VQ 코드북 품질 평가

        Args:
            codebook: 코드북 (K, D)
            features: 특징 벡터 (N, D)
            labels: 코드북 인덱스 (N,)

        Returns:
            평가 메트릭 딕셔너리
        """
        print("Evaluating VQ codebook quality...")

        metrics = {}

        # 코드북 크기
        metrics['codebook_size'] = codebook.shape[0]
        metrics['feature_dim'] = codebook.shape[1]

        # 평균 양자화 오차
        quantization_errors = []
        for i, label in enumerate(labels):
            error = np.linalg.norm(features[i] - codebook[label])
            quantization_errors.append(error)

        metrics['mean_quantization_error'] = float(np.mean(quantization_errors))
        metrics['std_quantization_error'] = float(np.std(quantization_errors))
        metrics['max_quantization_error'] = float(np.max(quantization_errors))

        # 코드 사용 분포
        code_usage = np.bincount(labels, minlength=len(codebook))
        metrics['code_usage_mean'] = float(np.mean(code_usage))
        metrics['code_usage_std'] = float(np.std(code_usage))
        metrics['unused_codes'] = int(np.sum(code_usage == 0))
        metrics['code_usage_entropy'] = float(self._entropy(code_usage))

        # 코드북 중복도 (코드 간 유사도)
        from scipy.spatial.distance import pdist
        code_distances = pdist(codebook, metric='euclidean')
        metrics['mean_inter_code_distance'] = float(np.mean(code_distances))
        metrics['std_inter_code_distance'] = float(np.std(code_distances))

        self.results['vq_codebook'] = metrics
        self._print_vq_summary(metrics)

        return metrics

    def _unsupervised_clustering_metrics(
        self,
        features: np.ndarray,
        labels: np.ndarray
    ) -> Dict:
        """비지도 학습 클러스터링 메트릭"""
        metrics = {}

        n_clusters = len(np.unique(labels))

        # 클러스터가 1개면 계산 불가
        if n_clusters <= 1:
            return {
                'n_clusters': n_clusters,
                'silhouette_score': None,
                'davies_bouldin_score': None,
                'calinski_harabasz_score': None
            }

        # 샘플링 (너무 많으면)
        if len(features) > 10000:
            sample_idx = np.random.choice(len(features), 10000, replace=False)
            sample_features = features[sample_idx]
            sample_labels = labels[sample_idx]
        else:
            sample_features = features
            sample_labels = labels

        try:
            # Silhouette Score (-1~1, 높을수록 좋음)
            metrics['silhouette_score'] = float(
                silhouette_score(sample_features, sample_labels)
            )
        except:
            metrics['silhouette_score'] = None

        try:
            # Davies-Bouldin Index (낮을수록 좋음)
            metrics['davies_bouldin_score'] = float(
                davies_bouldin_score(sample_features, sample_labels)
            )
        except:
            metrics['davies_bouldin_score'] = None

        try:
            # Calinski-Harabasz Index (높을수록 좋음)
            metrics['calinski_harabasz_score'] = float(
                calinski_harabasz_score(sample_features, sample_labels)
            )
        except:
            metrics['calinski_harabasz_score'] = None

        metrics['n_clusters'] = n_clusters

        return metrics

    def _supervised_clustering_metrics(
        self,
        predicted_labels: np.ndarray,
        true_labels: np.ndarray
    ) -> Dict:
        """지도 학습 클러스터링 메트릭"""
        from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

        metrics = {}

        try:
            # Adjusted Rand Index (0~1, 높을수록 좋음)
            metrics['adjusted_rand_index'] = float(
                adjusted_rand_score(true_labels, predicted_labels)
            )
        except:
            metrics['adjusted_rand_index'] = None

        try:
            # Normalized Mutual Information (0~1, 높을수록 좋음)
            metrics['normalized_mutual_info'] = float(
                normalized_mutual_info_score(true_labels, predicted_labels)
            )
        except:
            metrics['normalized_mutual_info'] = None

        return metrics

    def _supervised_change_detection_metrics(
        self,
        predicted: np.ndarray,
        ground_truth: np.ndarray
    ) -> Dict:
        """지도 학습 변화 탐지 메트릭"""
        metrics = {}

        # Confusion Matrix
        tn, fp, fn, tp = confusion_matrix(
            ground_truth, predicted, labels=[False, True]
        ).ravel()

        metrics['true_positive'] = int(tp)
        metrics['true_negative'] = int(tn)
        metrics['false_positive'] = int(fp)
        metrics['false_negative'] = int(fn)

        # 정확도, 정밀도, 재현율, F1
        metrics['accuracy'] = float(accuracy_score(ground_truth, predicted))
        metrics['precision'] = float(precision_score(ground_truth, predicted, zero_division=0))
        metrics['recall'] = float(recall_score(ground_truth, predicted, zero_division=0))
        metrics['f1_score'] = float(f1_score(ground_truth, predicted, zero_division=0))

        # 특이도
        metrics['specificity'] = float(tn / (tn + fp)) if (tn + fp) > 0 else 0.0

        # False Positive Rate
        metrics['false_positive_rate'] = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0

        return metrics

    def _magnitude_statistics(
        self,
        magnitudes: np.ndarray,
        mask: np.ndarray
    ) -> Dict:
        """변화 크기 통계"""
        changed_mag = magnitudes[mask]
        unchanged_mag = magnitudes[~mask]

        stats = {
            'magnitude_mean': float(np.mean(magnitudes)),
            'magnitude_std': float(np.std(magnitudes)),
            'magnitude_max': float(np.max(magnitudes)),
            'magnitude_min': float(np.min(magnitudes)),
            'magnitude_median': float(np.median(magnitudes))
        }

        if len(changed_mag) > 0:
            stats['changed_magnitude_mean'] = float(np.mean(changed_mag))
            stats['changed_magnitude_std'] = float(np.std(changed_mag))
        else:
            stats['changed_magnitude_mean'] = 0.0
            stats['changed_magnitude_std'] = 0.0

        if len(unchanged_mag) > 0:
            stats['unchanged_magnitude_mean'] = float(np.mean(unchanged_mag))
            stats['unchanged_magnitude_std'] = float(np.std(unchanged_mag))
        else:
            stats['unchanged_magnitude_mean'] = 0.0
            stats['unchanged_magnitude_std'] = 0.0

        return stats

    def _entropy(self, distribution: np.ndarray) -> float:
        """엔트로피 계산"""
        # 정규화
        probs = distribution / (np.sum(distribution) + 1e-10)
        probs = probs[probs > 0]  # 0 제거

        entropy = -np.sum(probs * np.log2(probs + 1e-10))
        return entropy

    def _print_clustering_summary(self, metrics: Dict):
        """클러스터링 평가 요약 출력"""
        print("\n=== Clustering Evaluation Summary ===")
        print(f"Number of clusters: {metrics.get('n_clusters', 'N/A')}")

        if metrics.get('silhouette_score') is not None:
            print(f"Silhouette Score: {metrics['silhouette_score']:.4f}")
        if metrics.get('davies_bouldin_score') is not None:
            print(f"Davies-Bouldin Index: {metrics['davies_bouldin_score']:.4f}")
        if metrics.get('calinski_harabasz_score') is not None:
            print(f"Calinski-Harabasz Index: {metrics['calinski_harabasz_score']:.2f}")

        if metrics.get('adjusted_rand_index') is not None:
            print(f"Adjusted Rand Index: {metrics['adjusted_rand_index']:.4f}")
        if metrics.get('normalized_mutual_info') is not None:
            print(f"Normalized Mutual Info: {metrics['normalized_mutual_info']:.4f}")

        print("=" * 40 + "\n")

    def _print_change_detection_summary(self, metrics: Dict):
        """변화 탐지 평가 요약 출력"""
        print("\n=== Change Detection Evaluation Summary ===")
        print(f"Total pixels: {metrics.get('n_total', 'N/A')}")
        print(f"Changed: {metrics.get('n_changed', 'N/A')} ({metrics.get('change_percentage', 0):.2f}%)")
        print(f"Unchanged: {metrics.get('n_unchanged', 'N/A')}")

        if metrics.get('accuracy') is not None:
            print(f"\nAccuracy: {metrics['accuracy']:.4f}")
            print(f"Precision: {metrics['precision']:.4f}")
            print(f"Recall: {metrics['recall']:.4f}")
            print(f"F1-Score: {metrics['f1_score']:.4f}")

        print("=" * 40 + "\n")

    def _print_vq_summary(self, metrics: Dict):
        """VQ 코드북 평가 요약 출력"""
        print("\n=== VQ Codebook Evaluation Summary ===")
        print(f"Codebook size: {metrics.get('codebook_size', 'N/A')}")
        print(f"Feature dimension: {metrics.get('feature_dim', 'N/A')}")
        print(f"Mean quantization error: {metrics.get('mean_quantization_error', 0):.4f}")
        print(f"Unused codes: {metrics.get('unused_codes', 0)}")
        print(f"Code usage entropy: {metrics.get('code_usage_entropy', 0):.4f}")
        print(f"Mean inter-code distance: {metrics.get('mean_inter_code_distance', 0):.4f}")
        print("=" * 40 + "\n")

    def get_all_results(self) -> Dict:
        """모든 평가 결과 반환"""
        return self.results

    def save_results(self, file_path: str):
        """결과를 JSON으로 저장"""
        with open(file_path, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"Results saved to {file_path}")

    def load_results(self, file_path: str):
        """JSON에서 결과 로드"""
        with open(file_path, 'r') as f:
            self.results = json.load(f)
        print(f"Results loaded from {file_path}")


class PerformanceTracker:
    """성능 추적 및 비교"""

    def __init__(self):
        self.history = []

    def add_experiment(
        self,
        name: str,
        config: Dict,
        metrics: Dict
    ):
        """실험 결과 추가"""
        self.history.append({
            'name': name,
            'config': config,
            'metrics': metrics
        })

    def compare_experiments(
        self,
        metric_key: str = 'f1_score'
    ) -> Dict:
        """실험 비교"""
        if not self.history:
            return {}

        comparison = {}
        for exp in self.history:
            name = exp['name']
            value = exp['metrics'].get(metric_key)
            if value is not None:
                comparison[name] = value

        # 정렬
        sorted_exp = sorted(comparison.items(), key=lambda x: x[1], reverse=True)

        print(f"\n=== Experiment Comparison ({metric_key}) ===")
        for i, (name, value) in enumerate(sorted_exp, 1):
            print(f"{i}. {name}: {value:.4f}")
        print("=" * 40 + "\n")

        return dict(sorted_exp)

    def get_best_experiment(
        self,
        metric_key: str = 'f1_score'
    ) -> Optional[Dict]:
        """최고 성능 실험 반환"""
        if not self.history:
            return None

        best_exp = max(
            self.history,
            key=lambda x: x['metrics'].get(metric_key, -float('inf'))
        )

        return best_exp

    def save_history(self, file_path: str):
        """히스토리 저장"""
        with open(file_path, 'w') as f:
            json.dump(self.history, f, indent=2)
        print(f"History saved to {file_path}")

    def load_history(self, file_path: str):
        """히스토리 로드"""
        with open(file_path, 'r') as f:
            self.history = json.load(f)
        print(f"History loaded from {file_path}")
