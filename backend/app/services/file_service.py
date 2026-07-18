import os
import shutil
from pathlib import Path
from typing import Dict, Optional
from PIL import Image
import numpy as np
from app.core.config import settings


class FileService:
    def __init__(self):
        self.upload_path = Path(settings.UPLOAD_PATH)
        self.upload_path.mkdir(parents=True, exist_ok=True)
        self.allowed_extensions = settings.ALLOWED_EXTENSIONS
        self.max_file_size = settings.MAX_FILE_SIZE
    
    async def validate_file(self, file) -> Dict:
        """파일 검증"""
        # 확장자 검증
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in self.allowed_extensions:
            return {
                "valid": False,
                "error": f"지원하지 않는 파일 형식입니다. 허용된 형식: {', '.join(self.allowed_extensions)}"
            }
        
        # 파일 크기 검증
        file.file.seek(0, 2)  # 파일 끝으로 이동
        file_size = file.file.tell()
        file.file.seek(0)  # 다시 시작으로
        
        if file_size > self.max_file_size:
            return {
                "valid": False,
                "error": f"파일 크기가 너무 큽니다. 최대 크기: {self.max_file_size / 1024 / 1024}MB"
            }
        
        return {"valid": True}
    
    async def save_file(self, file, user_id: str) -> str:
        """파일 저장"""
        # 사용자별 디렉토리 생성
        user_dir = self.upload_path / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        
        # 파일명 생성 (UUID 기반)
        import uuid
        file_ext = Path(file.filename).suffix
        filename = f"{uuid.uuid4()}{file_ext}"
        file_path = user_dir / filename
        
        # 파일 저장
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return str(file_path)
    
    async def extract_metadata(self, file_path: str) -> Dict:
        """메타데이터 추출"""
        metadata = {}
        
        try:
            with Image.open(file_path) as img:
                metadata["width"] = img.width
                metadata["height"] = img.height
                metadata["channels"] = len(img.getbands())
                metadata["format"] = img.format
                metadata["mode"] = img.mode
                
                # 파일 크기
                metadata["file_size"] = os.path.getsize(file_path)
                
        except Exception as e:
            metadata["error"] = str(e)
        
        return metadata
    
    async def generate_thumbnail(self, file_path: str, size: tuple = (256, 256)) -> str:
        """썸네일 생성"""
        thumbnail_dir = Path(settings.UPLOAD_PATH) / "thumbnails"
        thumbnail_dir.mkdir(parents=True, exist_ok=True)
        
        thumbnail_path = thumbnail_dir / f"{Path(file_path).stem}_thumb.jpg"
        
        try:
            with Image.open(file_path) as img:
                # RGB로 변환 (RGBA나 다른 모드인 경우)
                if img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')
                
                img.thumbnail(size, Image.Resampling.LANCZOS)
                img.save(thumbnail_path, "JPEG", quality=85)
        
        except Exception as e:
            raise Exception(f"썸네일 생성 실패: {str(e)}")
        
        return str(thumbnail_path)
