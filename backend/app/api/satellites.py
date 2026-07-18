import os
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.file_service import FileService
from app.tasks.vq_tasks import full_vq_pipeline_task

router = APIRouter()


@router.post("/upload")
async def upload_satellite_image(
    file_t1: UploadFile = File(...),
    file_t2: UploadFile = File(...),
    db: Session = Depends(get_db), # Keeping for consistency/auth if needed later
    current_user: User = Depends(get_current_user) # Keeping for consistency/auth if needed later
):
    \"\"\"두 시점 위성 영상 파일 업로드 및 VQ 파이프라인 시작\"\"\"
    
    file_service = FileService()

    # T1 파일 검증 및 저장
    validation_result_t1 = await file_service.validate_file(file_t1)
    if not validation_result_t1["valid"]:
        raise HTTPException(status_code=400, detail=f"T1 파일: {validation_result_t1['error']}")
    saved_path_t1 = await file_service.save_file(file_t1, current_user.id)

    # T2 파일 검증 및 저장
    validation_result_t2 = await file_service.validate_file(file_t2)
    if not validation_result_t2["valid"]:
        raise HTTPException(status_code=400, detail=f"T2 파일: {validation_result_t2['error']}")
    saved_path_t2 = await file_service.save_file(file_t2, current_user.id)
    
    # 결과 저장 디렉토리 생성
    job_id = str(uuid.uuid4())
    # Use environment variable or default to /tmp/vq-satellite/results
    output_dir = os.path.join(os.getenv("VQ_RESULTS_DIR", "/tmp/vq-satellite/results"), job_id)
    os.makedirs(output_dir, exist_ok=True)

    # 전체 VQ 파이프라인 작업 큐에 추가
    task = full_vq_pipeline_task.delay(
        image_t1_path=saved_path_t1,
        image_t2_path=saved_path_t2,
        output_dir=output_dir
    )
    
    return {
        "message": "VQ Full pipeline started successfully",
        "task_id": task.id,
        "job_id": job_id,
        "t1_filename": file_t1.filename,
        "t2_filename": file_t2.filename
    }
