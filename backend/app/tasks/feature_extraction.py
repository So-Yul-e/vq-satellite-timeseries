from celery import Task
from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.satellite import Satellite
from app.models.job import Job
from ml_service.src.processors.feature_extractor import FeatureExtractor
from ml_service.src.processors.vq_codebook import VQCodebookGenerator
import uuid


@celery_app.task(bind=True, name="extract_features")
def extract_features_task(self: Task, satellite_id: str):
    """특징 벡터 추출 및 VQ 코드북 생성 작업"""
    db = SessionLocal()
    
    try:
        # 위성 영상 조회
        satellite = db.query(Satellite).filter(Satellite.id == satellite_id).first()
        if not satellite:
            raise ValueError(f"위성 영상을 찾을 수 없습니다: {satellite_id}")
        
        # 작업 생성
        job = Job(
            id=uuid.uuid4(),
            user_id=satellite.user_id,
            job_type="feature_extraction",
            status="running",
            progress=0,
            input_data_json={"satellite_id": satellite_id}
        )
        db.add(job)
        db.commit()
        
        # 상태 업데이트
        satellite.status = "processing"
        db.commit()
        
        # 특징 추출기 초기화
        feature_extractor = FeatureExtractor()
        
        # 진행률 업데이트
        self.update_state(state="PROGRESS", meta={"progress": 10})
        job.progress = 10
        db.commit()
        
        # 특징 벡터 추출
        feature_vectors = feature_extractor.extract(satellite.file_path)
        
        self.update_state(state="PROGRESS", meta={"progress": 60})
        job.progress = 60
        db.commit()
        
        # VQ 코드북 생성
        codebook_generator = VQCodebookGenerator(codebook_size=256)
        codebook = codebook_generator.generate(feature_vectors)
        
        # 코드북 저장 (다음 워크플로우에서 구현)
        # ...
        
        self.update_state(state="PROGRESS", meta={"progress": 100})
        job.progress = 100
        job.status = "completed"
        satellite.status = "completed"
        db.commit()
        
        return {"status": "completed", "satellite_id": satellite_id}
    
    except Exception as e:
        if satellite:
            satellite.status = "failed"
        if job:
            job.status = "failed"
            job.error_message = str(e)
        db.commit()
        raise
    
    finally:
        db.close()
