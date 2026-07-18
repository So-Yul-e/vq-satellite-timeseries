from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional
from pathlib import Path
import os

# 과거 기본값 — 이 값이 실제로 설정돼 있으면 미설정으로 간주하고 fail-fast 처리
_INSECURE_SECRET_KEY_DEFAULTS = {"", "change-me-in-production"}


class Settings(BaseSettings):
    # 애플리케이션
    APP_NAME: str = "VQ Satellite Change Detection API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # 데이터베이스
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/dbname"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # 보안
    # 기본값을 두지 않는다 — .env/환경변수 미설정 시 아래 validator가 즉시 앱 시작을 중단시킨다 (fail-fast)
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24시간
    
    # 파일 업로드
    UPLOAD_PATH: str = "./uploads"
    MAX_FILE_SIZE: int = 524288000  # 500MB
    ALLOWED_EXTENSIONS: list = [".tif", ".tiff", ".jp2", ".png", ".jpg"]
    
    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"

    # External APIs
    SOLAR_API_KEY: str = "test_key"
    SOLAR_PERMIT_API_KEY: str = "test_permit_key"
    SOLAR_PERMIT_API_URL: str = "https://api.data.go.kr/openapi/tn_pubr_public_solar_gen_flct_api"
    
    # 산림청 API
    # DEPRECATED(2026-07-12): 산지 판정은 mountain_info_client.py가 VWorld 산림입지도로
    # 대체함(이름 검색 API라 좌표 판정이 구조적으로 불가능했음). backend/verify_api.py
    # 진단 스크립트가 참조하므로 필드는 유지하되 신규 코드에서 사용 금지.
    FOREST_MOUNTAIN_API_KEY: str = ""  # 산 정보 API 키 (.env에서 주입)
    FOREST_SERVICE_API_KEY: str = ""  # 산지정보시스템 API 키 (향후)
    FOREST_SERVICE_BASE_URL: str = "https://api.forest.go.kr"

    # VWorld(브이월드) 항공정사영상 Image API + 산림입지도 Data API(산지 판정)
    VWORLD_API_KEY: str = ""
    # VWorld API의 domain 검증값 — 인증키 발급 시 등록한 서비스 URL과 일치해야 함
    VWORLD_REQUEST_DOMAIN: str = "localhost"

    # 이메일
    MAIL_USERNAME: str = "your_email@gmail.com"
    MAIL_PASSWORD: str = "your_password"
    MAIL_FROM: str = "your_email@gmail.com"
    MAIL_PORT: int = 587
    MAIL_SERVER: str = "smtp.gmail.com"
    MAIL_FROM_NAME: str = "VQ Satellite Support"
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False
    USE_CREDENTIALS: bool = True
    VALIDATE_CERTS: bool = True
    # 개발 중에는 실제 메일을 보내지 않고 로그에만 출력하려면 True로 설정
    MAIL_SUPPRESS_SEND: bool = True
    
    class Config:
        # 프로젝트 루트 디렉토리의 .env 파일 경로 찾기
        # backend/app/core/config.py에서 프로젝트 루트로 이동
        _base_dir = Path(__file__).resolve().parent.parent.parent.parent  # backend/app/core -> 프로젝트 루트
        _env_path = _base_dir / ".env"
        
        # .env 파일이 존재하고 읽을 수 있으면 사용, 없으면 환경 변수만 사용
        env_file = str(_env_path) if _env_path.exists() and os.access(_env_path, os.R_OK) else None
        
        case_sensitive = True
        extra = "ignore"  # Ignore extra environment variables not defined in Settings

    @field_validator("SECRET_KEY")
    @classmethod
    def _validate_secret_key(cls, value: str) -> str:
        if not value or value in _INSECURE_SECRET_KEY_DEFAULTS:
            raise ValueError(
                "SECRET_KEY가 설정되지 않았거나 안전하지 않은 기본값입니다. "
                ".env에 강력한 랜덤 값을 SECRET_KEY로 설정하세요 "
                "(예: python -c \"import secrets; print(secrets.token_urlsafe(32))\")"
            )
        return value


settings = Settings()
