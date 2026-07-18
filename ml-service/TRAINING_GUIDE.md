# U-Net++ 태양광 패널 탐지 모델 학습 가이드

## 📋 개요

이 가이드는 U-Net++ 모델을 학습시켜 태양광 패널 세그멘테이션 >95% 정확도를 달성하는 방법을 설명합니다.

---

## 🎯 목표

- **정확도**: F1-Score > 95%
- **False Positive**: < 3%
- **처리 속도**: 1000km² < 10분

---

## 📦 1. 환경 설정

### 필수 패키지 설치

```bash
cd ml-service

# PyTorch (CUDA 11.8)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# 학습용 패키지
pip install albumentations==1.3.1
pip install pycocotools
pip install wandb  # 옵션: 실험 추적

# 기존 패키지 (requirements.txt)
pip install -r requirements.txt
```

### GPU 확인

```bash
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

---

## 📊 2. 데이터셋 준비

### 2-1. 추천 데이터셋

#### Option 1: Kaggle - Solar Panel Detection Dataset ⭐ 추천
- **URL**: https://www.kaggle.com/datasets/
- **크기**: ~5GB, 1000+ 이미지
- **포맷**: 이미지 + 마스크
- **라벨**: Binary (panel vs background)

```bash
# Kaggle CLI로 다운로드
kaggle datasets download -d <dataset-id>
unzip <dataset-id>.zip -d data/solar_panels
```

#### Option 2: Roboflow - Solar Panel Segmentation
- **URL**: https://universe.roboflow.com/
- **크기**: 커스터마이징 가능
- **포맷**: COCO, YOLO, Pascal VOC 등
- **장점**: 증강 자동 적용 가능

#### Option 3: 직접 라벨링
- **CVAT**: https://cvat.org/
- **LabelMe**: https://github.com/wkentaro/labelme
- **Roboflow Annotate**: https://roboflow.com/annotate

### 2-2. 데이터 구조

다운로드 후 다음과 같이 구조화:

```
data/
├── train/
│   ├── images/
│   │   ├── img001.jpg
│   │   ├── img002.jpg
│   │   └── ...
│   └── masks/
│       ├── img001.png  (binary: 0=background, 255=panel)
│       ├── img002.png
│       └── ...
└── val/
    ├── images/
    │   └── ...
    └── masks/
        └── ...
```

### 2-3. 데이터 검증

```bash
python -c "
import os
print('Train images:', len(os.listdir('data/train/images')))
print('Train masks:', len(os.listdir('data/train/masks')))
print('Val images:', len(os.listdir('data/val/images')))
print('Val masks:', len(os.listdir('data/val/masks')))
"
```

---

## 🚀 3. 학습 실행

### 3-1. 기본 학습

```bash
python train_unet.py \
  --train-images data/train/images \
  --train-masks data/train/masks \
  --val-images data/val/images \
  --val-masks data/val/masks \
  --epochs 100 \
  --batch-size 8 \
  --lr 1e-4 \
  --image-size 256 \
  --device cuda
```

### 3-2. 고급 설정 (고성능)

```bash
python train_unet.py \
  --train-images data/train/images \
  --train-masks data/train/masks \
  --val-images data/val/images \
  --val-masks data/val/masks \
  --epochs 150 \
  --batch-size 16 \
  --lr 1e-4 \
  --image-size 512 \
  --use-attention \
  --use-focal \
  --bce-weight 0.3 \
  --dice-weight 0.7 \
  --early-stopping 20 \
  --device cuda
```

### 3-3. NIR 채널 포함 (위성 영상)

```bash
python train_unet.py \
  --train-images data/train/images \
  --train-masks data/train/masks \
  --val-images data/val/images \
  --val-masks data/val/masks \
  --use-nir \
  --epochs 100 \
  --device cuda
```

### 3-4. 체크포인트에서 재개

```bash
python train_unet.py \
  --train-images data/train/images \
  --train-masks data/train/masks \
  --val-images data/val/images \
  --val-masks data/val/masks \
  --resume checkpoints/unet_plusplus_20251211_123456/best_f1.pth \
  --epochs 150
```

---

## 📈 4. 학습 모니터링

### 4-1. 로그 확인

```bash
# 실시간 로그
tail -f logs/unet_plusplus_*/training.log

# TensorBoard (옵션)
tensorboard --logdir logs/
```

### 4-2. 학습 진행 상황

학습 중 출력:
```
Epoch 10/100 [Train]: 100%|████| 125/125 [02:15<00:00, loss=0.2341]
Epoch 10/100 [Val]:   100%|████| 32/32 [00:25<00:00, f1=0.8912]

============================================================
Epoch 10/100
  Train Loss: 0.2341 (BCE: 0.1234, Dice: 0.1107)
  Val Loss: 0.1987
  Val Metrics:
    precision: 0.9123
    recall: 0.8712
    f1_score: 0.8912
    iou: 0.8034
    dice: 0.8912
  Learning Rate: 0.000100
============================================================

✓ Best F1 score! Saved checkpoint.
```

### 4-3. 체크포인트 파일

```
checkpoints/unet_plusplus_20251211_123456/
├── best_loss.pth        # 최저 validation loss
├── best_f1.pth          # 최고 F1 score ⭐ 사용 권장
├── checkpoint_epoch_5.pth
├── checkpoint_epoch_10.pth
└── interrupted.pth      # Ctrl+C 시 저장
```

---

## 🎓 5. 학습 결과 평가

### 5-1. 최종 메트릭 확인

```bash
# 학습 히스토리 확인
cat logs/unet_plusplus_*/training_history.json | jq '.val_metrics[-1]'
```

**출력 예시**:
```json
{
  "precision": 0.9612,
  "recall": 0.9543,
  "f1_score": 0.9577,
  "iou": 0.9183,
  "dice": 0.9577
}
```

✓ **F1 Score > 0.95 달성!**

### 5-2. 시각적 검증

```python
# 테스트 이미지로 예측
from models.advanced_solar_detector import AdvancedSolarDetector

detector = AdvancedSolarDetector(
    model_path='checkpoints/unet_plusplus_20251211_123456/best_f1.pth',
    device='cuda',
    confidence_threshold=0.5
)

# 예측
panels = detector.detect('test_image.tif')
print(f"Detected {len(panels)} panels")

# 시각화
detector.visualize_detection('test_image.tif', panels, 'output.png')
```

---

## ⚙️ 6. 하이퍼파라미터 튜닝

### 6-1. Loss 가중치 조정

```bash
# Recall 중시 (False Negative 줄이기)
--bce-weight 0.3 --dice-weight 0.7

# Precision 중시 (False Positive 줄이기)
--bce-weight 0.7 --dice-weight 0.3

# Focal Loss (불균형 데이터)
--use-focal --bce-weight 0.5 --dice-weight 0.5
```

### 6-2. 학습률 조정

```bash
# 느린 수렴 → 학습률 증가
--lr 5e-4

# 불안정 → 학습률 감소
--lr 5e-5

# Learning rate warmup (고급)
# trainer.py에서 구현 필요
```

### 6-3. 배치 크기

```bash
# GPU 메모리 부족 → 배치 감소
--batch-size 4

# GPU 여유 → 배치 증가
--batch-size 32
```

### 6-4. 이미지 크기

```bash
# 빠른 프로토타이핑
--image-size 128

# 고해상도 (정확도 향상)
--image-size 512  # or 1024
```

---

## 🐛 7. 문제 해결

### 7-1. Out of Memory (OOM)

```bash
# 배치 크기 줄이기
--batch-size 4

# 이미지 크기 줄이기
--image-size 128

# Gradient accumulation (고급)
# trainer.py 수정 필요
```

### 7-2. 과적합 (Overfitting)

증상: Train loss ↓↓, Val loss → 또는 ↑

**해결책**:
```bash
# 1. Weight decay 증가
--weight-decay 1e-4

# 2. Dropout 추가 (unet_plusplus.py 수정)
# 3. 데이터 증강 강화 (dataset.py 수정)
# 4. Early stopping
--early-stopping 10
```

### 7-3. 학습 안 됨 (Loss 감소 없음)

```bash
# 1. 학습률 증가
--lr 1e-3

# 2. Optimizer 변경 (trainer.py 수정)
optimizer = optim.SGD(model.parameters(), lr=1e-2, momentum=0.9)

# 3. Loss function 변경
--bce-weight 1.0 --dice-weight 0.0  # BCE만 사용
```

### 7-4. 데이터 로딩 느림

```bash
# Worker 수 증가
--num-workers 8

# 데이터 캐싱 (dataset.py 수정)
```

---

## 📊 8. 예상 학습 시간

### GPU별 시간 (1 epoch 기준)

| GPU | 1000 images | 10000 images |
|-----|-------------|--------------|
| **RTX 3090** | 2분 | 15분 |
| **RTX 4090** | 1.5분 | 10분 |
| **V100** | 3분 | 20분 |
| **A100** | 1분 | 8분 |
| **CPU** | 30분 | 4시간 ❌ |

### 총 학습 시간

- **빠른 프로토타입** (30 epochs): 1-2시간
- **고품질** (100 epochs): 3-6시간
- **최고 품질** (150+ epochs): 8-12시간

---

## 🎯 9. 목표 달성 체크리스트

### Phase 1: 데이터 준비 ✅
- [ ] 1000+ 라벨링된 이미지
- [ ] Train/Val split (80/20)
- [ ] 데이터 검증 완료

### Phase 2: 기본 학습 ✅
- [ ] 30 epochs 학습
- [ ] F1 Score > 0.80 달성
- [ ] 시각적 검증

### Phase 3: 고도화 ✅
- [ ] 100+ epochs 학습
- [ ] **F1 Score > 0.95 달성** ⭐
- [ ] False Positive < 3%
- [ ] 체크포인트 저장

### Phase 4: 배포 준비 ✅
- [ ] 최종 모델 선택 (best_f1.pth)
- [ ] 프로덕션 테스트
- [ ] Backend API 통합

---

## 💡 10. 추가 개선 방안

### 10-1. Test-Time Augmentation (TTA)

```python
# 예측 시 여러 증강 적용 → 평균
predictions = []
for aug in [flip_h, flip_v, rotate_90]:
    pred = model(augment(image))
    predictions.append(inverse_augment(pred))

final_pred = np.mean(predictions, axis=0)
```

### 10-2. Ensemble

```python
# 여러 모델 앙상블
models = [
    load_model('best_f1_run1.pth'),
    load_model('best_f1_run2.pth'),
    load_model('best_f1_run3.pth')
]

preds = [model(image) for model in models]
final_pred = np.mean(preds, axis=0)
```

### 10-3. Post-processing

```python
# Morphological operations
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

# Size filtering
contours = cv2.findContours(mask, ...)
filtered = [c for c in contours if MIN_AREA < cv2.contourArea(c) < MAX_AREA]
```

---

## 📚 11. 참고 자료

### 논문
- U-Net++: Zhou et al. (2018) "UNet++: A Nested U-Net Architecture for Medical Image Segmentation"
- Attention U-Net: Oktay et al. (2018) "Attention U-Net: Learning Where to Look for the Pancreas"
- Dice Loss: Milletari et al. (2016) "V-Net: Fully Convolutional Neural Networks for Volumetric Medical Image Segmentation"

### 데이터셋
- **Kaggle**: https://www.kaggle.com/search?q=solar+panel+in:datasets
- **Roboflow Universe**: https://universe.roboflow.com/
- **Google Dataset Search**: https://datasetsearch.research.google.com/

### 라벨링 도구
- **CVAT**: https://cvat.org/
- **LabelMe**: https://github.com/wkentaro/labelme
- **LabelImg**: https://github.com/tzutalin/labelImg

---

## 🆘 도움말

### 문제 발생 시
1. 이슈 등록: GitHub Issues
2. 로그 첨부: `logs/unet_plusplus_*/training.log`
3. 설정 공유: 실행한 명령어

### 추가 질문
- Discord/Slack 커뮤니티
- Stack Overflow (태그: unet, pytorch, segmentation)

---

**작성일**: 2025-12-11
**버전**: 1.0.0
**상태**: ✅ 학습 파이프라인 완성
