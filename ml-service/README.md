# ML Service - 태양광 패널 탐지

## YOLOv8 전국 태양광 패널 실시간 탐지

### 1. 모델 다운로드

먼저 YOLOv8 태양광 패널 탐지 모델을 다운로드합니다:

```bash
# Docker 컨테이너 내부에서 실행
docker exec -it vq-satellite-ml python download_yolov8_model.py
```

또는 호스트에서 실행:

```bash
cd ml-service
python download_yolov8_model.py
```

### 2. 테스트 실행 (전남 해남 1개 지역)

```bash
# Docker 컨테이너에서 실행
docker exec -it vq-satellite-ml python test_detection.py
```

또는 호스트에서:

```bash
cd ml-service
python test_detection.py
```

### 3. 전국 탐지 실행

```bash
# Docker 컨테이너에서 실행
docker exec -it vq-satellite-ml python detect_solar_panels.py
```

또는 호스트에서:

```bash
cd ml-service
python detect_solar_panels.py
```

## 주의사항

1. **GEE 인증**: Google Earth Engine 인증이 필요합니다
   - 서비스 계정 키 파일: `backend/gee-service-account.json`
   - 또는 `earthengine authenticate` 실행

2. **데이터베이스**: PostgreSQL이 실행 중이어야 합니다
   - `docker-compose up -d postgres`

3. **모델 파일**: YOLOv8 모델이 `./models/yolov8_solar_panels.pt`에 있어야 합니다

4. **API 제한**: GEE API 제한에 유의하세요 (스크립트는 자동으로 2초 간격 적용)

## 스크립트 설명

- `download_yolov8_model.py`: HuggingFace에서 YOLOv8 모델 다운로드
- `test_detection.py`: 전남 해남 1개 지역만 테스트
- `detect_solar_panels.py`: 전국 12개 주요 지역 스캔

## 환경 변수

```env
POSTGRES_HOST=postgres
POSTGRES_DB=vq_satellite
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
UNET_PRETRAINED_PATH=/app/models/unet_plusplus_solar_panels.pth  # 선택사항
```
