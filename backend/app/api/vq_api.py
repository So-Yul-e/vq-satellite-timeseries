"""VQ Clustering API 엔드포인트"""
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
import os
import uuid
from datetime import datetime

# 내장 샘플 이미지 경로 (backend/samples/) — git 커밋 대상, .gitignore(uploads)와 무관
SAMPLES_DIR = os.path.realpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "samples")
)
SAMPLE_T1_PATH = os.path.join(SAMPLES_DIR, "sample_t1.png")
SAMPLE_T2_PATH = os.path.join(SAMPLES_DIR, "sample_t2.png")

from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.vq_analysis_run import VqAnalysisRun
from app.tasks.vq_tasks import (
    extract_features_task,
    generate_codebook_task,
    clustering_task,
    detect_changes_task,
    full_vq_pipeline_task,
    location_vq_pipeline_task,
    timeseries_vq_pipeline_task,
)

router = APIRouter(prefix="/api/vq", tags=["VQ Clustering"])

# 임시 저장 디렉토리 — settings.UPLOAD_PATH를 단일 소스로 사용
UPLOAD_DIR = os.path.realpath(settings.UPLOAD_PATH)
RESULTS_DIR = os.path.realpath(os.path.join(UPLOAD_DIR, "results"))

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)


def validate_upload_path(path: str, field_name: str = "path") -> str:
    """
    사용자 입력 경로가 UPLOAD_PATH 하위인지 검증한다 (경로 화이트리스트).

    os.path.realpath로 심볼릭 링크/상대경로(../)를 모두 해석한 뒤
    UPLOAD_DIR/RESULTS_DIR prefix 내에 있는지 확인한다. 벗어나면 422.
    """
    if not path:
        raise HTTPException(
            status_code=422,
            detail={"detail": f"{field_name}이(가) 비어 있습니다", "code": "E-422-INVALID_PATH"},
        )

    resolved = os.path.realpath(path)
    allowed_roots = (UPLOAD_DIR, RESULTS_DIR)

    if not any(
        resolved == root or resolved.startswith(root + os.sep)
        for root in allowed_roots
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "detail": f"{field_name}은(는) 업로드 디렉토리 하위 경로만 허용됩니다",
                "code": "E-422-PATH_NOT_ALLOWED",
            },
        )

    return resolved


def validate_upload_file(file: UploadFile, content: bytes) -> None:
    """확장자(ALLOWED_EXTENSIONS)와 크기(MAX_FILE_SIZE)를 검증한다."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail={
                "detail": f"허용되지 않는 파일 확장자입니다: {ext}",
                "code": "E-415-UNSUPPORTED_MEDIA_TYPE",
            },
        )

    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail={
                "detail": f"파일 용량이 최대 허용치({settings.MAX_FILE_SIZE} bytes)를 초과했습니다",
                "code": "E-413-PAYLOAD_TOO_LARGE",
            },
        )


# Pydantic 스키마
class FeatureExtractionRequest(BaseModel):
    image_path: str


class CodebookGenerationRequest(BaseModel):
    features_path: str
    codebook_size: int = 256


class ClusteringRequest(BaseModel):
    features_path: str
    n_clusters: int = 8
    algorithm: str = "kmeans"  # kmeans, dbscan, hierarchical


class ChangeDetectionRequest(BaseModel):
    features_t1_path: str
    features_t2_path: str
    codebook_t1_path: str
    codebook_t2_path: str
    threshold_method: str = "otsu"  # otsu, adaptive


class FullPipelineRequest(BaseModel):
    image_t1_path: str = ""
    image_t2_path: str = ""
    codebook_size: int = 256
    n_clusters: int = 8
    use_sample: bool = False


class TimeseriesPipelineRequest(BaseModel):
    """연속(다시점) VQ 시계열 요청 — 여러 연도 같은 계절을 훑는다."""
    latitude: float
    longitude: float
    buffer_km: float = 2.0
    start_year: int
    end_year: int
    month: int = 5  # 같은 계절(월)


class LocationPipelineRequest(BaseModel):
    """좌표+과거날짜 기반 시계열 변화탐지 요청 (프로젝트 본래 목적)."""
    latitude: float
    longitude: float
    buffer_km: float = 2.0
    past_date: str  # YYYY-MM-DD, 비교할 과거 시점(T1)
    current_date: str = ""  # 비우면 오늘(T2)
    codebook_size: int = 256
    n_clusters: int = 8


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: Optional[int] = None
    result: Optional[dict] = None
    error: Optional[str] = None


# API 엔드포인트

@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    """
    이미지 업로드

    Returns:
        업로드된 파일 정보
    """
    try:
        content = await file.read()
        validate_upload_file(file, content)

        # 파일명 생성
        file_id = str(uuid.uuid4())
        file_ext = os.path.splitext(file.filename)[1]
        file_path = os.path.join(UPLOAD_DIR, f"{file_id}{file_ext}")

        # 파일 저장
        with open(file_path, "wb") as f:
            f.write(content)

        return {
            "file_id": file_id,
            "file_path": file_path,
            "filename": file.filename,
            "size": len(content),
            "uploaded_at": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-features", response_model=dict)
async def extract_features(
    request: FeatureExtractionRequest,
    current_user=Depends(get_current_user),
):
    """
    특징 벡터 추출 (비동기 작업)

    Returns:
        Celery 작업 ID
    """
    try:
        image_path = validate_upload_path(request.image_path, "image_path")

        # 출력 경로 생성
        job_id = str(uuid.uuid4())
        output_path = os.path.join(RESULTS_DIR, job_id, "features.npy")

        # Celery 작업 시작
        task = extract_features_task.delay(image_path, output_path)

        return {
            "task_id": task.id,
            "job_id": job_id,
            "status": "started",
            "message": "Feature extraction task started"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-codebook", response_model=dict)
async def generate_codebook(
    request: CodebookGenerationRequest,
    current_user=Depends(get_current_user),
):
    """
    VQ 코드북 생성 (비동기 작업)

    Returns:
        Celery 작업 ID
    """
    try:
        features_path = validate_upload_path(request.features_path, "features_path")

        job_id = str(uuid.uuid4())
        output_path = os.path.join(RESULTS_DIR, job_id, "codebook.pkl")

        task = generate_codebook_task.delay(
            features_path,
            output_path,
            request.codebook_size
        )

        return {
            "task_id": task.id,
            "job_id": job_id,
            "status": "started",
            "message": "Codebook generation task started"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cluster", response_model=dict)
async def cluster(
    request: ClusteringRequest,
    current_user=Depends(get_current_user),
):
    """
    클러스터링 (비동기 작업)

    Returns:
        Celery 작업 ID
    """
    try:
        features_path = validate_upload_path(request.features_path, "features_path")

        job_id = str(uuid.uuid4())
        output_path = os.path.join(RESULTS_DIR, job_id, "cluster_result.pkl")

        task = clustering_task.delay(
            features_path,
            output_path,
            request.n_clusters,
            request.algorithm
        )

        return {
            "task_id": task.id,
            "job_id": job_id,
            "status": "started",
            "message": f"Clustering task started with {request.algorithm}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/detect-changes", response_model=dict)
async def detect_changes(
    request: ChangeDetectionRequest,
    current_user=Depends(get_current_user),
):
    """
    변화 탐지 (비동기 작업)

    Returns:
        Celery 작업 ID
    """
    try:
        features_t1_path = validate_upload_path(request.features_t1_path, "features_t1_path")
        features_t2_path = validate_upload_path(request.features_t2_path, "features_t2_path")
        codebook_t1_path = validate_upload_path(request.codebook_t1_path, "codebook_t1_path")
        codebook_t2_path = validate_upload_path(request.codebook_t2_path, "codebook_t2_path")

        job_id = str(uuid.uuid4())
        output_path = os.path.join(RESULTS_DIR, job_id, "change_result.pkl")

        task = detect_changes_task.delay(
            features_t1_path,
            features_t2_path,
            codebook_t1_path,
            codebook_t2_path,
            output_path,
            request.threshold_method
        )

        return {
            "task_id": task.id,
            "job_id": job_id,
            "status": "started",
            "message": "Change detection task started"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/full-pipeline", response_model=dict)
async def full_pipeline(
    request: FullPipelineRequest,
    current_user=Depends(get_current_user),
):
    """
    전체 VQ Clustering 파이프라인 실행

    Args:
        request: 두 시점의 이미지 경로 및 파라미터

    Returns:
        Celery 작업 ID
    """
    try:
        if request.use_sample:
            # 내장 샘플 사용 — 경로 검증(UPLOAD_DIR 화이트리스트) 건너뛰고
            # backend/samples/의 고정 이미지 2장을 그대로 사용한다.
            for label, path in (("sample_t1", SAMPLE_T1_PATH), ("sample_t2", SAMPLE_T2_PATH)):
                if not os.path.exists(path):
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "detail": f"내장 샘플 파일을 찾을 수 없습니다: {label}",
                            "code": "E-500-SAMPLE_NOT_FOUND",
                        },
                    )
            image_t1_path = SAMPLE_T1_PATH
            image_t2_path = SAMPLE_T2_PATH
        else:
            image_t1_path = validate_upload_path(request.image_t1_path, "image_t1_path")
            image_t2_path = validate_upload_path(request.image_t2_path, "image_t2_path")

        job_id = str(uuid.uuid4())
        output_dir = os.path.join(RESULTS_DIR, job_id)

        task = full_vq_pipeline_task.delay(
            image_t1_path,
            image_t2_path,
            output_dir,
            request.codebook_size,
            request.n_clusters
        )

        return {
            "task_id": task.id,
            "job_id": job_id,
            "status": "started",
            "message": "Full VQ pipeline started",
            "estimated_time": "5-10 minutes"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-location", response_model=dict)
async def analyze_location(
    request: LocationPipelineRequest,
    current_user=Depends(get_current_user),
):
    """
    좌표+과거날짜 기반 시계열 변화탐지 (프로젝트 본래 목적).

    같은 지점의 과거(T1)·현재(T2) 위성영상을 GEE에서 받아 VQ 클러스터링으로
    무엇이 바뀌었는지 탐지한다. 결과는 /api/vq/task/{task_id}로 폴링.
    """
    try:
        import re
        for label, val in (("past_date", request.past_date), ("current_date", request.current_date)):
            if val and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
                raise HTTPException(
                    status_code=422,
                    detail={"detail": f"{label}는 YYYY-MM-DD 형식이어야 합니다", "code": "E-422-INVALID_DATE"},
                )
        if not (-90 <= request.latitude <= 90 and -180 <= request.longitude <= 180):
            raise HTTPException(
                status_code=422,
                detail={"detail": "좌표 범위가 올바르지 않습니다", "code": "E-422-INVALID_COORD"},
            )
        if not (0.2 <= request.buffer_km <= 10):
            raise HTTPException(
                status_code=422,
                detail={"detail": "buffer_km는 0.2~10 사이여야 합니다", "code": "E-422-INVALID_BUFFER"},
            )

        job_id = str(uuid.uuid4())
        output_dir = os.path.join(RESULTS_DIR, job_id)

        task = location_vq_pipeline_task.delay(
            request.latitude,
            request.longitude,
            request.buffer_km,
            request.past_date,
            request.current_date,
            output_dir,
            request.codebook_size,
            request.n_clusters,
        )

        return {
            "task_id": task.id,
            "job_id": job_id,
            "status": "started",
            "message": "위치 기반 시계열 변화탐지 시작",
            "estimated_time": "3-8 minutes",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-timeseries", response_model=dict)
async def analyze_timeseries(
    request: TimeseriesPipelineRequest,
    current_user=Depends(get_current_user),
):
    """연속(다시점) VQ 시계열 변화탐지 — 같은 지점의 여러 연도를 훑어 언제 바뀌었는지.

    결과는 /api/vq/task/{task_id}로 폴링. result.timeseries.frames에 연도별 이미지·변화.
    """
    try:
        from datetime import date
        y0, y1 = int(request.start_year), int(request.end_year)
        if y1 < y0:
            raise HTTPException(status_code=422, detail={"detail": "end_year는 start_year 이상이어야 합니다", "code": "E-422-YEAR_RANGE"})
        if (y1 - y0 + 1) > 10:
            raise HTTPException(status_code=422, detail={"detail": "연도 범위는 최대 10년입니다(부하 제한)", "code": "E-422-YEAR_SPAN"})
        if y0 < 2016 or y1 > date.today().year:
            raise HTTPException(status_code=422, detail={"detail": "연도는 2016~올해 사이여야 합니다(Sentinel-2 가용 범위)", "code": "E-422-YEAR_BOUND"})
        if not (1 <= request.month <= 12):
            raise HTTPException(status_code=422, detail={"detail": "month는 1~12여야 합니다", "code": "E-422-MONTH"})
        if not (-90 <= request.latitude <= 90 and -180 <= request.longitude <= 180):
            raise HTTPException(status_code=422, detail={"detail": "좌표 범위가 올바르지 않습니다", "code": "E-422-INVALID_COORD"})
        if not (0.2 <= request.buffer_km <= 10):
            raise HTTPException(status_code=422, detail={"detail": "buffer_km는 0.2~10 사이여야 합니다", "code": "E-422-INVALID_BUFFER"})

        job_id = str(uuid.uuid4())
        output_dir = os.path.join(RESULTS_DIR, job_id)
        task = timeseries_vq_pipeline_task.delay(
            request.latitude, request.longitude, request.buffer_km,
            y0, y1, request.month, output_dir,
        )
        return {"task_id": task.id, "job_id": job_id, "status": "started",
                "message": "연속 시계열 변화탐지 시작", "estimated_time": "3-10 minutes"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs")
async def list_vq_runs(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """최근 VQ 위치 분석 실행 목록(요약) — 결과가 휘발되지 않고 즉시 재표시하기 위함."""
    limit = max(1, min(limit, 100))
    rows = db.query(VqAnalysisRun).order_by(VqAnalysisRun.created_at.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": str(r.id),
                "latitude": r.latitude,
                "longitude": r.longitude,
                "buffer_km": r.buffer_km,
                "past_date": r.past_date,
                "current_date": r.t2_date,
                "n_total": r.n_total,
                "n_changed": r.n_changed,
                "change_percentage": r.change_percentage,
                "solar_panel_count": r.solar_panel_count,
                "n_solar_patches": r.n_solar_patches,
                "created_at": (r.created_at.isoformat() + "Z") if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.get("/runs/{run_id}")
async def get_vq_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """저장된 VQ 분석 결과 전체(task result와 동일 shape) — 목록 클릭 시 즉시 재표시."""
    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="run_id 형식이 올바르지 않습니다")
    row = db.query(VqAnalysisRun).filter(VqAnalysisRun.id == rid).first()
    if row is None:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다")
    # 프론트가 폴링 결과와 동일하게 다루도록 {status, result} 형태로 반환
    return {"status": "SUCCESS", "result": row.result_json}


@router.get("/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user=Depends(get_current_user),
):
    """
    작업 상태 조회

    Args:
        task_id: Celery 작업 ID

    Returns:
        작업 상태 정보
    """
    from celery.result import AsyncResult
    from app.core.celery_app import celery_app

    try:
        task = AsyncResult(task_id, app=celery_app)

        response = {
            "task_id": task_id,
            "status": task.state
        }

        if task.state == "PENDING":
            response["progress"] = 0
        elif task.state == "PROGRESS":
            response["progress"] = task.info.get("progress", 0)
            response["result"] = task.info
        elif task.state == "SUCCESS":
            response["progress"] = 100
            response["result"] = task.result
        elif task.state == "FAILURE":
            response["error"] = str(task.info)

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/task/{task_id}")
async def cancel_task(
    task_id: str,
    current_user=Depends(get_current_user),
):
    """
    작업 취소

    Args:
        task_id: Celery 작업 ID

    Returns:
        취소 결과
    """
    from celery.result import AsyncResult
    from app.core.celery_app import celery_app

    try:
        task = AsyncResult(task_id, app=celery_app)
        task.revoke(terminate=True)

        return {
            "task_id": task_id,
            "status": "cancelled",
            "message": "Task cancelled successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check 엔드포인트"""
    return {
        "status": "ok",
        "service": "VQ Clustering API",
        "timestamp": datetime.utcnow().isoformat()
    }
