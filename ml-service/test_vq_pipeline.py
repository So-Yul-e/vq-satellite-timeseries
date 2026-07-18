"""VQ Clustering 파이프라인 통합 테스트"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import numpy as np
from PIL import Image
import argparse
from pathlib import Path

from processors.feature_extractor import FeatureExtractor
from processors.vq_codebook import VQCodebookGenerator
from processors.clustering import ClusteringProcessor
from processors.change_detection import ChangeDetector
from evaluation.metrics import MetricsEvaluator, PerformanceTracker


def create_dummy_images(output_dir: str = "test_data"):
    """테스트용 더미 이미지 생성"""
    os.makedirs(output_dir, exist_ok=True)

    # 512x512 크기의 랜덤 이미지 2개 생성
    img1 = np.random.randint(0, 256, (512, 512, 3), dtype=np.uint8)
    img2 = img1.copy()

    # 두 번째 이미지에 변화 추가 (일부 영역을 밝게)
    img2[100:200, 100:200] = np.clip(img2[100:200, 100:200] + 50, 0, 255)

    # 저장
    img1_path = os.path.join(output_dir, "image_t1.png")
    img2_path = os.path.join(output_dir, "image_t2.png")

    Image.fromarray(img1).save(img1_path)
    Image.fromarray(img2).save(img2_path)

    print(f"✓ Dummy images created in {output_dir}/")
    return img1_path, img2_path


def test_feature_extraction():
    """특징 추출 테스트"""
    print("\n" + "="*60)
    print("Test 1: Feature Extraction")
    print("="*60)

    # 더미 이미지 생성
    img1_path, img2_path = create_dummy_images()

    # 특징 추출기 초기화
    extractor = FeatureExtractor(device='cpu')

    # 특징 추출
    features_t1 = extractor.extract(img1_path)
    features_t2 = extractor.extract(img2_path)

    print(f"✓ Features extracted from t1: {features_t1.shape}")
    print(f"✓ Features extracted from t2: {features_t2.shape}")

    return features_t1, features_t2


def test_vq_codebook(features):
    """VQ 코드북 생성 테스트"""
    print("\n" + "="*60)
    print("Test 2: VQ Codebook Generation")
    print("="*60)

    # VQ 코드북 생성기 초기화
    vq_generator = VQCodebookGenerator(codebook_size=64, use_minibatch=False)

    # 코드북 생성
    codebook = vq_generator.generate(features)

    # 벡터 양자화
    indices = vq_generator.quantize(features)

    # 메트릭 출력
    metrics = vq_generator.get_metrics()
    print(f"✓ Codebook shape: {codebook.shape}")
    print(f"✓ Silhouette Score: {metrics.get('silhouette_score', 'N/A')}")
    print(f"✓ Inertia: {metrics.get('inertia', 0):.2f}")

    # 코드북 저장
    os.makedirs("test_data", exist_ok=True)
    vq_generator.save_codebook("test_data/codebook.pkl")

    return codebook, indices, vq_generator


def test_clustering(features):
    """클러스터링 테스트"""
    print("\n" + "="*60)
    print("Test 3: Clustering")
    print("="*60)

    # K-means 클러스터링
    kmeans_processor = ClusteringProcessor(algorithm='kmeans')
    kmeans_result = kmeans_processor.cluster(features, n_clusters=8)

    print(f"✓ K-means clusters: {kmeans_result['n_clusters']}")
    print(f"✓ Inertia: {kmeans_result['inertia']:.2f}")
    print(f"✓ Silhouette Score: {kmeans_result.get('silhouette_score', 'N/A')}")

    return kmeans_result


def test_change_detection(features_t1, features_t2, codebook_t1, codebook_t2):
    """변화 탐지 테스트"""
    print("\n" + "="*60)
    print("Test 4: Change Detection")
    print("="*60)

    # 변화 탐지기 초기화
    detector = ChangeDetector(
        threshold_method='otsu',
        spatial_smoothing=True
    )

    # 변화 탐지
    change_result = detector.detect_changes(
        features_t1=features_t1,
        features_t2=features_t2,
        codebook_t1=codebook_t1,
        codebook_t2=codebook_t2
    )

    print(f"✓ Total pixels: {change_result['statistics']['n_total']}")
    print(f"✓ Changed pixels: {change_result['statistics']['n_changed']}")
    print(f"✓ Change percentage: {change_result['statistics']['change_percentage']:.2f}%")
    print(f"✓ Threshold: {change_result['threshold']:.4f}")

    # 결과 저장
    detector.save_results(change_result, "test_data/change_detection_result.pkl")

    return change_result


def test_evaluation(features, labels, change_mask):
    """평가 메트릭 테스트"""
    print("\n" + "="*60)
    print("Test 5: Evaluation Metrics")
    print("="*60)

    evaluator = MetricsEvaluator()

    # 클러스터링 평가
    clustering_metrics = evaluator.evaluate_clustering(
        features=features,
        labels=labels
    )

    # 변화 탐지 평가
    change_metrics = evaluator.evaluate_change_detection(
        predicted_mask=change_mask
    )

    # 결과 저장
    evaluator.save_results("test_data/evaluation_results.json")

    return evaluator


def test_full_pipeline():
    """전체 파이프라인 테스트"""
    print("\n" + "="*60)
    print("FULL VQ CLUSTERING PIPELINE TEST")
    print("="*60)

    try:
        # 1. 특징 추출
        features_t1, features_t2 = test_feature_extraction()

        # 2. VQ 코드북 생성 (두 시점 각각)
        print("\n>>> Generating codebook for t1...")
        codebook_t1, indices_t1, vq_gen_t1 = test_vq_codebook(features_t1)

        print("\n>>> Generating codebook for t2...")
        codebook_t2, indices_t2, vq_gen_t2 = test_vq_codebook(features_t2)

        # 3. 클러스터링
        clustering_result = test_clustering(features_t1)

        # 4. 변화 탐지
        change_result = test_change_detection(
            features_t1, features_t2,
            codebook_t1, codebook_t2
        )

        # 5. 평가
        evaluator = test_evaluation(
            features=features_t1,
            labels=indices_t1,
            change_mask=change_result['change_mask']
        )

        # 최종 요약
        print("\n" + "="*60)
        print("✓ ALL TESTS PASSED!")
        print("="*60)
        print("\nGenerated files in test_data/:")
        print("  - image_t1.png, image_t2.png")
        print("  - codebook.pkl")
        print("  - change_detection_result.pkl")
        print("  - evaluation_results.json")

        return True

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_with_real_images(image1_path: str, image2_path: str):
    """실제 이미지로 테스트"""
    print("\n" + "="*60)
    print("TESTING WITH REAL IMAGES")
    print("="*60)
    print(f"Image 1: {image1_path}")
    print(f"Image 2: {image2_path}")

    try:
        # 특징 추출
        extractor = FeatureExtractor(device='cpu')
        features_t1 = extractor.extract(image1_path)
        features_t2 = extractor.extract(image2_path)

        print(f"✓ Features t1: {features_t1.shape}")
        print(f"✓ Features t2: {features_t2.shape}")

        # VQ 코드북
        vq_gen = VQCodebookGenerator(codebook_size=128)
        codebook_t1 = vq_gen.generate(features_t1)
        indices_t1 = vq_gen.quantize(features_t1)

        codebook_t2 = vq_gen.generate(features_t2)
        indices_t2 = vq_gen.quantize(features_t2)

        # 변화 탐지
        detector = ChangeDetector(threshold_method='otsu')
        change_result = detector.detect_changes(
            features_t1, features_t2,
            codebook_t1, codebook_t2
        )

        print(f"\n✓ Change detected: {change_result['statistics']['change_percentage']:.2f}%")

        # 결과 저장
        output_dir = "test_data/real_images_result"
        os.makedirs(output_dir, exist_ok=True)
        detector.save_results(change_result, f"{output_dir}/change_result.pkl")

        print(f"\n✓ Results saved to {output_dir}/")

        return True

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='VQ Clustering Pipeline Test')
    parser.add_argument('--mode', choices=['dummy', 'real'], default='dummy',
                        help='Test mode: dummy (synthetic images) or real (actual images)')
    parser.add_argument('--image1', type=str, help='Path to first image (for real mode)')
    parser.add_argument('--image2', type=str, help='Path to second image (for real mode)')

    args = parser.parse_args()

    if args.mode == 'dummy':
        # 더미 이미지로 전체 파이프라인 테스트
        success = test_full_pipeline()
    else:
        # 실제 이미지로 테스트
        if not args.image1 or not args.image2:
            print("Error: --image1 and --image2 are required for real mode")
            sys.exit(1)

        success = test_with_real_images(args.image1, args.image2)

    sys.exit(0 if success else 1)
