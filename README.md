<!-- 언어 전환 -->
**🇰🇷 한국어** · [🇺🇸 English](./README.en.md)

# VQ 위성 시계열 변화탐지 · 태양광 모니터링

벡터 양자화(Vector Quantization) 코드북으로 위성 영상의 **시계열 변화를 탐지**하고, 고해상 항공영상 + YOLOv8로 **태양광 시설을 교차확인**하는 웹 서비스입니다. Google Earth Engine의 Sentinel-2를 받아 한 지점을 여러 해에 걸쳐 훑으며 "어디가, 언제, 어떻게 바뀌었나"를 보여줍니다.

> 개인 포트폴리오/연구용 프로젝트입니다. Google Earth Engine·공공데이터는 각 서비스 약관을 따릅니다(GEE는 비상업 무료 범위).

---

## 핵심 기능

### 1. VQ 연속(다시점) 시계열 변화탐지
- 한 좌표를 **여러 연도(같은 계절)**에 걸쳐 받아, 전체를 합쳐 **VQ 코드북 1개**를 학습합니다.
- 각 시점을 코드워드에 양자화하고, **코드워드 할당이 바뀐 패치를 변화로 판정**합니다 — 판정의 주역이 VQ 코드북입니다(단순 픽셀 차이가 아님).
- 타임라인 슬라이더로 연도를 훑으면 변화가 누적돼 보이고, "패치별 처음 바뀐 연도" 분포로 **언제** 변화가 일어났는지 압니다.

### 2. 계절·날씨 노이즈 정규화
- **계절 정합**: 비교 시점을 자동으로 같은 절기(같은 월)로 맞춰 식생 위상 차이를 제거합니다.
- **Radiometric normalization**: 프레임 간 밝기·대비를 정렬해 조도·대기 흐림 차이가 변화로 오인되지 않게 합니다.

### 3. YOLO 교차참조 — 정직한 의미 라벨
- VQ는 "무엇의 변화인지" 짐작하지 않습니다(비지도). 대신 같은 좌표의 **고해상 항공영상(VWorld)에 YOLOv8**을 돌려 태양광 패널을 탐지하고, VQ 변화 패치와 겹치면 **"태양광 확인"**으로 표시합니다 — 짐작이 아니라 독립 모델의 실측입니다.

### 4. AI 태양광 탐지 · 허가 매칭
- YOLOv8-seg으로 태양광 패널을 탐지하고, 공공 허가 데이터(약 11만 건)와 좌표 매칭해 **무허가 의심** 여부를 스크리닝합니다(확정 아님).
- 경사도·산림·수계 기반 위험도 평가(보조 신호), 전국 통계.

### 5. 결과 영속화
- 분석(1~2분 소요)을 저장해 새로고침 후에도 남고, **"최근 분석" 목록**에서 클릭 한 번으로 즉시 재표시합니다.

---

## 스크린샷

| 연속 시계열 타임라인 | 변화 인스펙터 (태양광 마커) |
|---|---|
| ![연속 시계열 타임라인 — 연도 슬라이더 + 변화 발생 시점 막대](docs/images/timeline.png) | ![변화 인스펙터 — 강도/그룹 + 태양광 노란 테두리](docs/images/inspector.png) |

| AI 탐지 지도 | 허가 데이터 / 무허가 관리 |
|---|---|
| ![AI 탐지 — 상태별 마커 + 범례](docs/images/detection.png) | ![무허가 관리 — 목록 + 지도](docs/images/permits.png) |

---

## 아키텍처

```
Next.js 14 (프론트)  ──►  FastAPI (백엔드)  ──►  PostgreSQL/PostGIS
                                │
                                ├─► Celery + Redis (비동기: VQ 파이프라인·동기화)
                                ├─► Google Earth Engine (Sentinel-2 시계열)
                                ├─► VWorld (고해상 항공영상 · 산림입지도)
                                └─► YOLOv8-seg (태양광 탐지) · ResNet50 (특징)
```

**스택**: Next.js 14 · TypeScript · Tailwind / FastAPI · SQLAlchemy 2.0 · Celery 5 / PostgreSQL + PostGIS · Redis / PyTorch 2.2 · ultralytics(YOLOv8) · scikit-learn · earthengine-api

---

## 기술 하이라이트

- **VQ 코드북이 변화 판정의 주역** — shared 코드북으로 두(또는 N개) 시점을 같은 어휘로 양자화, 할당 변화로 탐지. 프로젝트 이름값을 실제 구현.
- **비지도의 정직한 경계** — 변화의 종류는 판정하지 않고, 태양광만 독립 YOLO 실측으로 라벨. "모르는 걸 아는 척" 안 함.
- **PostGIS 공간 매칭** — ST_DWithin + GIST 인덱스로 패널-허가 매칭.
- **멱등 데이터 동기화** — 공공 허가 데이터 주간 자동 동기화(전량 교체 + 재매칭, 트랜잭션·SAVEPOINT).

---

## 빠른 시작

### 사전 요구사항
- Docker & Docker Compose
- Google Earth Engine 서비스 계정 키(`backend/gee-service-account.json`) — 비상업 무료
- VWorld · 공공데이터포털 API 키

### 실행
```bash
# 1) 루트에 .env 작성 (아래 예시 참고)
# 2) GEE 서비스 계정 키를 backend/gee-service-account.json 에 배치
# 3) 기동
docker compose up -d
# 프론트: http://localhost:3002 · API 문서: http://localhost:8000/api/docs
```

`.env` 주요 항목:
```bash
POSTGRES_USER=...  POSTGRES_PASSWORD=...  POSTGRES_DB=...
SECRET_KEY=<강한 랜덤 값>
VWORLD_API_KEY=...  VWORLD_REQUEST_DOMAIN=localhost
SOLAR_PERMIT_API_KEY=...  SOLAR_PERMIT_API_URL=...
```

> 참고: 최초 기동 후 DB 마이그레이션(`database/migrations/*.sql`)과 허가 데이터 임포트가 필요합니다.

---

## 프로젝트 구조

```
backend/        FastAPI · Celery 태스크 · 서비스(GEE·VWorld·YOLO·매칭)
ml-service/     VQ 코드북 · 특징 추출 · 변화탐지 processors
frontend/       Next.js 14 대시보드 (5탭)
database/       PostGIS 마이그레이션
docs/images/     README 스크린샷
```

---

## 한계 · 디스클레이머

- **비지도 변화탐지**라 정규화 후에도 잔여 계절/식생 변화가 일부 잡힐 수 있습니다. 변화의 "종류"는 판정하지 않습니다(태양광 제외 — 별도 YOLO 실측).
- **"무허가 의심"은 스크리닝 신호이지 위법 확정이 아닙니다**(매칭 실패의 결과). 행정 판단의 근거로 쓰지 마세요.
- **GEE는 비상업 무료** 범위에서만 사용합니다. 상업 이용은 별도 라이선스 필요.
- 정확도(정밀도/재현율)의 정답 대비 정량 평가는 아직 없습니다 — "동작"은 검증됐으나 "정확도 수치"는 미측정.

---

## 라이선스

**AGPL-3.0** — 핵심 탐지 모델인 [ultralytics(YOLOv8)](https://github.com/ultralytics/ultralytics)가 AGPL-3.0이라, 이를 결합한 본 저장소도 같은 라이선스로 배포합니다. 의존성별 라이선스와 외부 데이터 약관은 [NOTICE.md](./NOTICE.md) 참조.
