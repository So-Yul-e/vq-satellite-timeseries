import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.api import users, detections, admin, auth_simple, gee, solar, vq_api, solar_panels_api, risk_assessment_api, solar_permits_api, matching_api
from app.core.config import settings
from app.core.rate_limit import limiter

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth_simple.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(gee.router, prefix="/api/gee", tags=["Google Earth Engine"])
app.include_router(solar.router, prefix="/api/solar", tags=["Solar Panel Detection"])
app.include_router(vq_api.router, tags=["VQ Clustering"])
app.include_router(solar_panels_api.router, tags=["Solar Panels - Nationwide"])
app.include_router(solar_permits_api.router, prefix="/api", tags=["Solar Permits - Public Data"])
app.include_router(matching_api.router, prefix="/api", tags=["Panel-Permit Matching"])
app.include_router(risk_assessment_api.router, prefix="/api/risk", tags=["Risk Assessment"])
# app.include_router(satellites.router, prefix="/api/satellites", tags=["satellites"])
app.include_router(detections.router, prefix="/api/detections", tags=["detections"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])

# VQ 파이프라인 결과 이미지(T1/T2/변화 오버레이) 서빙 — UPLOAD_PATH 하위만 노출
# (vq_api.py의 경로 화이트리스트와 동일 경계, 업로드/생성 이미지 외 노출 없음)
os.makedirs(settings.UPLOAD_PATH, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_PATH), name="uploads")


@app.get("/")
async def root():
    return {
        "message": "VQ Satellite Change Detection API",
        "version": settings.APP_VERSION
    }


@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}
