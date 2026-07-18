# YOLOv8 모델 성능 평가 가이드

## 📋 개요

YOLOv8 태양광 패널 탐지 모델의 정확도를 평가하고 개선 방향을 제시합니다.

## 🚀 평가 실행 방법

### 1. 사전 준비

#### GEE 인증 확인
```bash
# 서비스 계정 키 파일 확인
ls backend/gee-service-account.json
```

#### YOLOv8 모델 다운로드
```bash
# Docker 환경
docker exec -it vq-satellite-ml python download_yolov8_model.py

# 로컬 환경
cd ml-service
python download_yolov8_model.py
```

### 2. 평가 실행

```bash
# Docker 환경에서 실행 (권장)
docker exec -it vq-satellite-ml python evaluate_yolov8.py

# 로컬 환경
cd ml-service
python evaluate_yolov8.py
```

### 3. 결과 확인

평가가 완료되면 다음 파일들이 생성됩니다:

- `./test_images/`: 다운로드한 테스트 위성 영상
- `./evaluation_results.json`: 평가 결과 JSON

## 📊 평가 지표 설명

### 1. Precision (정밀도)
- **의미**: 모델이 "태양광 패널이다"라고 탐지한 것 중 실제로 태양광 패널인 비율
- **공식**: TP / (TP + FP)
- **해석**: 높을수록 오탐지가 적음
- **목표**: ≥ 85%

### 2. Recall (재현율)
- **의미**: 실제 태양광 패널 중에서 모델이 탐지한 비율
- **공식**: TP / (TP + FN)
- **해석**: 높을수록 미탐지가 적음
- **목표**: ≥ 80%

### 3. F1-Score
- **의미**: Precision과 Recall의 조화 평균
- **공식**: 2 × (Precision × Recall) / (Precision + Recall)
- **해석**: 전반적인 성능 지표
- **목표**: ≥ 80%

### 4. 평가 등급

| F1-Score | 등급 | 설명 | 조치 |
|----------|------|------|------|
| ≥ 80% | 🟢 우수 | 프로덕션 사용 가능 | 현재 모델 유지 |
| 60-80% | 🟡 양호 | Fine-tuning 권장 | 데이터 추가 학습 |
| 40-60% | 🟠 보통 | 추가 학습 필요 | 모델 개선 필수 |
| < 40% | 🔴 낮음 | 사용 부적합 | 모델 재선택 |

## 🔧 모델 개선 방안

### Option 1: YOLOv8 Fine-tuning (추천)

현재 YOLOv8 모델을 한국 위성 영상 데이터로 추가 학습

**장점**:
- 비교적 적은 데이터로도 개선 가능 (100-500장)
- 학습 시간 짧음 (1-2일)
- 기존 모델의 지식 활용

**단점**:
- 라벨링 작업 필요
- GPU 필수

**구현 방법**:
```python
# fine_tune_yolov8.py
from ultralytics import YOLO

# 사전 학습된 모델 로드
model = YOLO('./models/yolov8_solar_panels.pt')

# 한국 데이터로 Fine-tuning
model.train(
    data='./data/korea_solar_panels.yaml',  # 데이터셋 설정
    epochs=50,
    imgsz=640,
    batch=16,
    device=0  # GPU
)
```

### Option 2: U-Net++ 학습

시맨틱 세그멘테이션 모델로 더 정밀한 탐지

**장점**:
- 픽셀 단위 정확도
- 복잡한 형태 탐지 가능

**단점**:
- 많은 데이터 필요 (500-1000장)
- 학습 시간 길음 (3-7일)
- 더 많은 라벨링 작업

**현재 상태**:
- 모델 구조는 구현됨 (`src/models/unet_plusplus.py`)
- 학습 스크립트 필요
- 학습 데이터셋 필요

### Option 3: 앙상블 (Ensemble)

YOLOv8 + SimpleSolarDetector 조합

**장점**:
- 추가 학습 불필요
- 정확도 즉시 개선 가능

**단점**:
- 추론 속도 느림
- False Positive 증가 가능

**구현 방법**:
```python
# YOLOv8 탐지
yolo_detections = model_yolo.predict(image)

# SimpleSolarDetector 탐지
simple_detections = detector_simple.detect(image)

# 두 결과를 NMS (Non-Maximum Suppression)으로 병합
final_detections = merge_detections(yolo_detections, simple_detections)
```

### Option 4: Segment Anything Model (SAM) 활용

최신 제로샷 세그멘테이션 모델

**장점**:
- 추가 학습 불필요
- 범용성 높음

**단점**:
- 추론 속도 느림
- 메모리 많이 사용

## 📈 권장 개선 로드맵

### Phase 1: 현재 성능 파악 (완료)
- ✅ 평가 스크립트 작성
- ⏳ 실제 데이터로 평가 실행
- ⏳ F1-Score, Precision, Recall 측정

### Phase 2: 빠른 개선 (F1 < 60%인 경우)

**A. 하이퍼파라미터 튜닝** (1일)
```python
# 신뢰도 임계값 조정
results = model.predict(image, conf=0.25)  # 기본값 0.3에서 낮춤

# IoU 임계값 조정
results = model.predict(image, iou=0.5)  # 기본값 0.45에서 높임
```

**B. 앙상블 적용** (2-3일)
- YOLOv8 + SimpleSolarDetector 조합
- NMS 파라미터 최적화

### Phase 3: 본격 개선 (F1 60-80%인 경우)

**A. Fine-tuning 데이터 준비** (1주)
1. 한국 위성 영상 100-200장 수집
2. 라벨링 도구로 태양광 패널 표시 (LabelImg, CVAT)
3. YOLOv8 데이터셋 형식으로 변환

**B. Fine-tuning 실행** (2-3일)
1. 학습 스크립트 작성
2. GPU 서버에서 학습 실행
3. 검증 데이터로 성능 평가

### Phase 4: 고급 개선 (F1 < 60%인 경우)

**A. U-Net++ 학습** (2-3주)
1. 데이터셋 확장 (500-1000장)
2. 픽셀 단위 라벨링
3. 모델 학습 및 평가

**B. 최신 모델 도입** (2-4주)
- Mask R-CNN
- Segment Anything Model (SAM)
- YOLOv9/v10 시도

## 🎯 즉시 실행 가능한 개선

### 1. 신뢰도 임계값 최적화

현재 `conf=0.3`을 사용 중입니다. 다양한 값으로 테스트:

```python
# detect_solar_panels.py 수정
results = model.predict(
    image,
    conf=0.25,  # 0.3 → 0.25로 낮춰서 더 많이 탐지
    iou=0.45,
    imgsz=640
)
```

### 2. 이미지 해상도 조정

```python
# 고해상도로 탐지 (더 작은 패널 탐지 가능)
results = model.predict(
    image,
    conf=0.3,
    iou=0.45,
    imgsz=1024  # 640 → 1024
)
```

### 3. 후처리 필터 추가

```python
def filter_detections(detections, min_area=100, max_area=50000):
    """
    비정상적인 탐지 결과 필터링
    """
    filtered = []
    for det in detections:
        bbox = det['bbox']
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])

        # 면적 필터
        if min_area <= area <= max_area:
            # 종횡비 필터 (태양광 패널은 대체로 직사각형)
            aspect_ratio = (bbox[2] - bbox[0]) / (bbox[3] - bbox[1])
            if 0.3 <= aspect_ratio <= 5.0:
                filtered.append(det)

    return filtered
```

## 📊 평가 결과 해석

평가 스크립트 실행 후 다음과 같은 결과가 나옵니다:

```
📊 YOLOv8 모델 평가 리포트
==================================================

📈 기본 통계:
  - 총 테스트 이미지: 7개
  - 탐지 성공 이미지: 4개
  - 탐지 실패 이미지: 3개
  - 평균 탐지 개수: 2.57개/이미지
  - 평균 신뢰도: 68.5%

🎯 분류 결과:
  - True Positives (올바른 탐지): 4개
  - False Positives (오탐지): 1개
  - False Negatives (미탐지): 2개

📊 성능 지표:
  - Precision (정밀도): 80.0%
  - Recall (재현율): 66.7%
  - F1-Score: 72.7%
  - Accuracy (정확도): 57.1%

💡 평가:
  - 종합 평가: 🟡 양호 (F1 ≥ 60%)
  - 권장사항: 모델 성능이 양호하나, Fine-tuning으로 개선 가능합니다.
```

### 결과 분석

1. **Precision 80%**: 모델이 탐지한 것 중 80%는 실제 태양광 패널 → 오탐지 낮음 ✅
2. **Recall 66.7%**: 실제 태양광 패널 중 66.7%만 탐지 → 미탐지 문제 있음 ⚠️
3. **F1-Score 72.7%**: 양호하나 개선 필요

### 개선 방향

- **Recall 향상**: 신뢰도 임계값 낮추기 (`conf=0.3 → 0.25`)
- **Fine-tuning**: 한국 데이터로 추가 학습

## 🛠️ 다음 단계

1. **평가 실행**: `python evaluate_yolov8.py`
2. **결과 분석**: F1-Score 확인
3. **개선 선택**:
   - F1 ≥ 80%: 현재 모델 유지
   - F1 60-80%: 하이퍼파라미터 튜닝 + Fine-tuning 고려
   - F1 < 60%: Fine-tuning 필수 또는 모델 재선택

## 📚 참고 자료

- [YOLOv8 공식 문서](https://docs.ultralytics.com/)
- [Fine-tuning 가이드](https://docs.ultralytics.com/modes/train/)
- [커스텀 데이터셋 준비](https://docs.ultralytics.com/datasets/)
