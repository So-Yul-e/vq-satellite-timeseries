"""
YOLOv8 태양광 패널 탐지 모델 성능 평가
실제 위성 영상으로 정확도, 재현율, mAP 측정
"""
import ee
import os
import sys
from pathlib import Path
from ultralytics import YOLO
from datetime import datetime, timedelta
import httpx
from PIL import Image
import io
import json
import numpy as np
import time
from typing import List, Dict, Tuple

# GEE 초기화
def init_gee():
    """Google Earth Engine 초기화"""
    try:
        service_account_key = '/app/gee-service-account.json'
        if os.path.exists(service_account_key):
            with open(service_account_key, 'r') as f:
                key_data = json.load(f)
                service_account_email = key_data.get('client_email')

            credentials = ee.ServiceAccountCredentials(
                email=service_account_email,
                key_file=service_account_key
            )
            ee.Initialize(credentials)
            print(f"✅ GEE 초기화 성공: {service_account_email}")
            return True
        else:
            ee.Initialize()
            print("✅ GEE 기본 인증 성공")
            return True
    except Exception as e:
        print(f"❌ GEE 초기화 실패: {e}")
        return False


def download_test_images(test_locations: List[Dict], buffer_km: float = 5.0) -> List[Dict]:
    """
    테스트용 위성 영상 다운로드

    Args:
        test_locations: 테스트 위치 리스트 [{"name": ..., "lat": ..., "lon": ..., "has_panels": bool}]
        buffer_km: 영상 범위 (km)

    Returns:
        다운로드된 영상 정보 리스트
    """
    print("\n📥 테스트 영상 다운로드 중...")
    downloaded = []

    for loc in test_locations:
        print(f"\n  🛰️  {loc['name']} 다운로드 중...")

        try:
            # 관심 지역 설정
            point = ee.Geometry.Point([loc['lon'], loc['lat']])
            aoi = point.buffer(buffer_km * 1000)

            # 최근 6개월 영상
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')

            # Sentinel-2 영상 가져오기
            collection = (
                ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(aoi)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
                .sort('CLOUDY_PIXEL_PERCENTAGE')
            )

            count = collection.size().getInfo()
            if count == 0:
                print(f"    ⚠️  영상 없음, 건너뛰기")
                continue

            # 가장 구름 적은 영상 선택
            image = collection.first()

            # RGB 영상으로 변환
            rgb = image.select(['B4', 'B3', 'B2'])

            # 썸네일 URL 생성
            url = rgb.getThumbURL({
                'region': aoi.getInfo()['coordinates'],
                'dimensions': 1024,
                'format': 'jpg'
            })

            # 영상 다운로드
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url)
                if response.status_code == 200:
                    img = Image.open(io.BytesIO(response.content))

                    # 파일로 저장
                    save_path = f"./test_images/{loc['name'].replace(' ', '_')}.jpg"
                    os.makedirs("./test_images", exist_ok=True)
                    img.save(save_path)

                    downloaded.append({
                        'name': loc['name'],
                        'image_path': save_path,
                        'has_panels': loc.get('has_panels', True),
                        'lat': loc['lat'],
                        'lon': loc['lon'],
                        'expected_count': loc.get('expected_count', None)
                    })

                    print(f"    ✅ 저장 완료: {save_path}")
                else:
                    print(f"    ❌ 다운로드 실패: HTTP {response.status_code}")

        except Exception as e:
            print(f"    ❌ 오류: {e}")

        # API 제한 방지
        time.sleep(2)

    return downloaded


def evaluate_model_on_images(model: YOLO, test_images: List[Dict]) -> Dict:
    """
    YOLOv8 모델 평가

    Args:
        model: YOLOv8 모델
        test_images: 테스트 영상 리스트

    Returns:
        평가 결과 딕셔너리
    """
    print("\n🤖 모델 평가 중...")

    results_summary = {
        'total_images': len(test_images),
        'detections_per_image': [],
        'confidence_scores': [],
        'true_positives': 0,
        'false_positives': 0,
        'false_negatives': 0,
        'images_with_detection': 0,
        'images_without_detection': 0
    }

    detailed_results = []

    for img_info in test_images:
        print(f"\n  📷 {img_info['name']} 평가 중...")

        # YOLOv8 추론
        results = model.predict(
            img_info['image_path'],
            conf=0.3,  # 신뢰도 임계값
            iou=0.45,
            imgsz=640,
            verbose=False
        )

        detections = []
        if len(results) > 0:
            result = results[0]
            if result.boxes is not None and len(result.boxes) > 0:
                for box in result.boxes:
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()

                    detections.append({
                        'bbox': [x1, y1, x2, y2],
                        'confidence': conf,
                        'area': (x2 - x1) * (y2 - y1)
                    })

                    results_summary['confidence_scores'].append(conf)

        num_detections = len(detections)
        results_summary['detections_per_image'].append(num_detections)

        # 탐지 여부 판단
        has_detection = num_detections > 0
        expected_panels = img_info.get('has_panels', True)

        if has_detection:
            results_summary['images_with_detection'] += 1
        else:
            results_summary['images_without_detection'] += 1

        # True Positive / False Positive / False Negative 계산
        if expected_panels and has_detection:
            results_summary['true_positives'] += 1
            result_type = "✅ True Positive (올바른 탐지)"
        elif expected_panels and not has_detection:
            results_summary['false_negatives'] += 1
            result_type = "❌ False Negative (미탐지)"
        elif not expected_panels and has_detection:
            results_summary['false_positives'] += 1
            result_type = "⚠️  False Positive (오탐지)"
        else:
            result_type = "✅ True Negative (올바른 미탐지)"

        print(f"    탐지 개수: {num_detections}")
        print(f"    결과: {result_type}")

        # 상세 결과 저장
        detailed_results.append({
            'name': img_info['name'],
            'num_detections': num_detections,
            'expected_panels': expected_panels,
            'result_type': result_type,
            'detections': detections
        })

    return results_summary, detailed_results


def calculate_metrics(results_summary: Dict) -> Dict:
    """
    평가 지표 계산 (Precision, Recall, F1-Score)
    """
    tp = results_summary['true_positives']
    fp = results_summary['false_positives']
    fn = results_summary['false_negatives']

    # Precision = TP / (TP + FP)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0

    # Recall = TP / (TP + FN)
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    # F1-Score = 2 * (Precision * Recall) / (Precision + Recall)
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    # Accuracy = (TP + TN) / Total
    # 여기서는 이미지 레벨 정확도
    accuracy = tp / results_summary['total_images'] if results_summary['total_images'] > 0 else 0.0

    # 평균 신뢰도
    avg_confidence = np.mean(results_summary['confidence_scores']) if results_summary['confidence_scores'] else 0.0

    # 평균 탐지 개수
    avg_detections = np.mean(results_summary['detections_per_image']) if results_summary['detections_per_image'] else 0.0

    return {
        'precision': precision,
        'recall': recall,
        'f1_score': f1_score,
        'accuracy': accuracy,
        'avg_confidence': avg_confidence,
        'avg_detections_per_image': avg_detections
    }


def print_evaluation_report(results_summary: Dict, metrics: Dict, detailed_results: List[Dict]):
    """평가 리포트 출력"""
    print("\n" + "="*70)
    print("📊 YOLOv8 모델 평가 리포트")
    print("="*70)

    print(f"\n📈 기본 통계:")
    print(f"  - 총 테스트 이미지: {results_summary['total_images']}개")
    print(f"  - 탐지 성공 이미지: {results_summary['images_with_detection']}개")
    print(f"  - 탐지 실패 이미지: {results_summary['images_without_detection']}개")
    print(f"  - 평균 탐지 개수: {metrics['avg_detections_per_image']:.2f}개/이미지")
    print(f"  - 평균 신뢰도: {metrics['avg_confidence']:.2%}")

    print(f"\n🎯 분류 결과:")
    print(f"  - True Positives (올바른 탐지): {results_summary['true_positives']}개")
    print(f"  - False Positives (오탐지): {results_summary['false_positives']}개")
    print(f"  - False Negatives (미탐지): {results_summary['false_negatives']}개")

    print(f"\n📊 성능 지표:")
    print(f"  - Precision (정밀도): {metrics['precision']:.2%}")
    print(f"    → 탐지한 것 중 실제로 태양광 패널인 비율")
    print(f"  - Recall (재현율): {metrics['recall']:.2%}")
    print(f"    → 실제 태양광 패널 중 탐지한 비율")
    print(f"  - F1-Score: {metrics['f1_score']:.2%}")
    print(f"    → Precision과 Recall의 조화 평균")
    print(f"  - Accuracy (정확도): {metrics['accuracy']:.2%}")
    print(f"    → 전체 이미지 중 올바르게 판단한 비율")

    print(f"\n💡 평가:")
    if metrics['f1_score'] >= 0.8:
        grade = "🟢 우수 (F1 ≥ 80%)"
        recommendation = "모델 성능이 우수합니다. 프로덕션 사용 가능합니다."
    elif metrics['f1_score'] >= 0.6:
        grade = "🟡 양호 (F1 ≥ 60%)"
        recommendation = "모델 성능이 양호하나, Fine-tuning으로 개선 가능합니다."
    elif metrics['f1_score'] >= 0.4:
        grade = "🟠 보통 (F1 ≥ 40%)"
        recommendation = "모델 성능이 보통입니다. 추가 학습이 권장됩니다."
    else:
        grade = "🔴 낮음 (F1 < 40%)"
        recommendation = "모델 성능이 낮습니다. 다른 모델 검토 또는 재학습이 필요합니다."

    print(f"  - 종합 평가: {grade}")
    print(f"  - 권장사항: {recommendation}")

    print(f"\n📋 상세 결과:")
    for detail in detailed_results:
        print(f"  - {detail['name']}: {detail['num_detections']}개 탐지 → {detail['result_type']}")

    print("="*70)


def main():
    """메인 함수"""
    print("="*70)
    print("🔬 YOLOv8 태양광 패널 탐지 모델 성능 평가")
    print("="*70)

    # 1. GEE 초기화
    print("\n1️⃣ Google Earth Engine 초기화...")
    if not init_gee():
        print("❌ GEE 초기화 실패. 종료합니다.")
        return

    # 2. YOLOv8 모델 로드
    print("\n2️⃣ YOLOv8 모델 로드...")
    model_path = "./models/yolov8_solar_panels.pt"
    if not os.path.exists(model_path):
        print(f"❌ 모델 파일을 찾을 수 없습니다: {model_path}")
        print("💡 먼저 download_yolov8_model.py를 실행하세요")
        return

    model = YOLO(model_path)
    print(f"✅ 모델 로드 완료")

    # 3. 테스트 위치 정의
    print("\n3️⃣ 테스트 위치 설정...")

    # 다양한 지역 테스트 (태양광 패널이 있는 곳 + 없는 곳)
    test_locations = [
        # 태양광 패널이 많은 지역
        {"name": "전남 해남 (태양광 밀집)", "lat": 34.5700, "lon": 126.5900, "has_panels": True},
        {"name": "전남 영암 (태양광 밀집)", "lat": 34.8004, "lon": 126.6964, "has_panels": True},
        {"name": "강원 영월 (산지 태양광)", "lat": 37.1830, "lon": 128.4600, "has_panels": True},
        {"name": "충남 당진 (평지 태양광)", "lat": 36.8926, "lon": 126.6478, "has_panels": True},

        # 태양광 패널이 거의 없는 지역 (False Positive 테스트)
        {"name": "서울 강남 (도심)", "lat": 37.4979, "lon": 127.0276, "has_panels": False},
        {"name": "제주 한라산 (자연)", "lat": 33.3617, "lon": 126.5292, "has_panels": False},
        {"name": "경기 수원 (주거)", "lat": 37.2636, "lon": 127.0286, "has_panels": False},
    ]

    print(f"  총 {len(test_locations)}개 지역 테스트 예정")

    # 4. 테스트 영상 다운로드
    test_images = download_test_images(test_locations, buffer_km=3.0)

    if not test_images:
        print("❌ 다운로드된 테스트 영상이 없습니다.")
        return

    print(f"\n✅ {len(test_images)}개 테스트 영상 준비 완료")

    # 5. 모델 평가
    results_summary, detailed_results = evaluate_model_on_images(model, test_images)

    # 6. 지표 계산
    metrics = calculate_metrics(results_summary)

    # 7. 리포트 출력
    print_evaluation_report(results_summary, metrics, detailed_results)

    # 8. 결과를 JSON으로 저장
    output_file = "./evaluation_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'summary': results_summary,
            'metrics': metrics,
            'detailed_results': detailed_results,
            'timestamp': datetime.now().isoformat()
        }, f, indent=2, ensure_ascii=False)

    print(f"\n💾 평가 결과 저장: {output_file}")
    print("\n✅ 평가 완료!")


if __name__ == "__main__":
    main()
