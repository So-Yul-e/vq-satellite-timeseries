# Third-Party Notices

이 프로젝트는 아래 오픈소스·외부 서비스 위에서 동작합니다. 각 구성요소는 자체 라이선스/약관을 따릅니다.

## 라이선스 결정 근거

핵심 탐지 모델로 사용하는 **ultralytics(YOLOv8)가 AGPL-3.0**입니다. AGPL은 이를 결합해
네트워크 서비스로 제공하는 소프트웨어에도 소스 공개 의무를 지우는 강한 copyleft이므로,
본 저장소 전체를 **AGPL-3.0**으로 배포합니다. (YOLO 가중치 파일 자체는 이 저장소에
포함·재배포하지 않습니다.)

## 주요 의존성

| 구성요소 | 라이선스 |
|---|---|
| ultralytics (YOLOv8) | **AGPL-3.0** |
| PyTorch · torchvision | BSD-3-Clause |
| scikit-learn · scipy · numpy · shapely | BSD-3-Clause |
| FastAPI · pydantic · SQLAlchemy · Celery · Next.js · React · Tailwind CSS | MIT |
| earthengine-api · requests · huggingface_hub | Apache-2.0 |
| OpenCV (opencv-python-headless) | Apache-2.0 |
| psycopg2 | LGPL-3.0 |
| PostgreSQL · PostGIS | PostgreSQL License / GPL-2.0 |

(전체 목록은 `backend/requirements.txt` · `ml-service/requirements.txt` · `frontend/package.json` 참조)

## 외부 데이터·서비스 약관 (라이선스와 별개)

- **Google Earth Engine** (Sentinel-2): 비상업(non-commercial) 무료 범위에서만 사용.
  상업 이용은 Google과의 별도 라이선스 필요.
- **VWorld** (고해상 항공영상·산림입지도): 국토교통부 VWorld 오픈API 이용약관 적용.
- **공공데이터포털** (태양광 발전 허가 데이터): 각 데이터셋의 이용허락 조건 적용.

본 저장소의 AGPL-3.0은 **코드에만** 적용되며, 위 데이터·서비스 사용 권한을 부여하지 않습니다.
