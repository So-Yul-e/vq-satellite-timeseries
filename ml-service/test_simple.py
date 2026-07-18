"""간단한 유닛 테스트 (torch 없이)"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import numpy as np

def test_vq_codebook():
    """VQ 코드북 테스트 (numpy만 사용)"""
    print("\n=== Testing VQ Codebook ===")

    from processors.vq_codebook import VQCodebookGenerator

    # 더미 특징 벡터 생성 (100개, 128차원)
    features = np.random.randn(100, 128).astype(np.float32)

    # VQ 코드북 생성
    vq_gen = VQCodebookGenerator(codebook_size=16)
    codebook = vq_gen.generate(features)

    print(f"✓ Codebook shape: {codebook.shape}")
    assert codebook.shape == (16, 128), "Codebook shape mismatch"

    # 양자화
    indices = vq_gen.quantize(features)
    print(f"✓ Indices shape: {indices.shape}")
    assert len(indices) == 100, "Indices length mismatch"
    assert np.max(indices) < 16, "Index out of range"

    # 메트릭
    metrics = vq_gen.get_metrics()
    print(f"✓ Silhouette Score: {metrics.get('silhouette_score', 'N/A')}")
    print(f"✓ Inertia: {metrics.get('inertia', 0):.2f}")

    print("✓ VQ Codebook test PASSED\n")
    return True


def test_clustering():
    """클러스터링 테스트"""
    print("\n=== Testing Clustering ===")

    from processors.clustering import ClusteringProcessor

    # 더미 특징 벡터
    features = np.random.randn(100, 128).astype(np.float32)

    # K-means 클러스터링
    processor = ClusteringProcessor(algorithm='kmeans')
    result = processor.cluster(features, n_clusters=8)

    print(f"✓ Number of clusters: {result['n_clusters']}")
    print(f"✓ Labels shape: {result['labels'].shape}")
    print(f"✓ Centers shape: {result['centers'].shape}")

    assert result['n_clusters'] == 8, "Cluster count mismatch"
    assert len(result['labels']) == 100, "Labels length mismatch"
    assert result['centers'].shape == (8, 128), "Centers shape mismatch"

    print("✓ Clustering test PASSED\n")
    return True


def test_change_detection():
    """변화 탐지 테스트"""
    print("\n=== Testing Change Detection ===")

    from processors.change_detection import ChangeDetector

    # 더미 특징 벡터 (두 시점)
    features_t1 = np.random.randn(100, 128).astype(np.float32)
    features_t2 = features_t1 + np.random.randn(100, 128) * 0.1  # 약간의 변화

    # 코드북
    codebook_t1 = np.random.randn(16, 128).astype(np.float32)
    codebook_t2 = codebook_t1 + np.random.randn(16, 128) * 0.05

    # 변화 탐지
    detector = ChangeDetector(threshold_method='adaptive')
    result = detector.detect_changes(
        features_t1, features_t2,
        codebook_t1, codebook_t2
    )

    print(f"✓ Change magnitudes shape: {result['change_magnitudes'].shape}")
    print(f"✓ Change mask shape: {result['change_mask'].shape}")
    print(f"✓ Threshold: {result['threshold']:.4f}")
    print(f"✓ Changed: {result['statistics']['n_changed']} / {result['statistics']['n_total']}")

    assert len(result['change_magnitudes']) == 100, "Magnitude length mismatch"
    assert len(result['change_mask']) == 100, "Mask length mismatch"

    print("✓ Change Detection test PASSED\n")
    return True


def test_metrics():
    """평가 메트릭 테스트"""
    print("\n=== Testing Evaluation Metrics ===")

    from evaluation.metrics import MetricsEvaluator

    # 더미 데이터
    features = np.random.randn(100, 128).astype(np.float32)
    labels = np.random.randint(0, 8, 100)
    change_mask = np.random.rand(100) > 0.5

    evaluator = MetricsEvaluator()

    # 클러스터링 평가
    clustering_metrics = evaluator.evaluate_clustering(features, labels)
    print(f"✓ Clustering metrics: {len(clustering_metrics)} metrics calculated")

    # 변화 탐지 평가
    change_metrics = evaluator.evaluate_change_detection(change_mask)
    print(f"✓ Change detection metrics: {len(change_metrics)} metrics calculated")

    print("✓ Evaluation Metrics test PASSED\n")
    return True


def main():
    print("="*60)
    print("VQ CLUSTERING UNIT TESTS (without PyTorch)")
    print("="*60)

    tests = [
        ("VQ Codebook", test_vq_codebook),
        ("Clustering", test_clustering),
        ("Change Detection", test_change_detection),
        ("Evaluation Metrics", test_metrics)
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {name} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60)

    if failed == 0:
        print("\n✓ ALL TESTS PASSED! 🎉")
        return True
    else:
        print(f"\n❌ {failed} test(s) failed")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
