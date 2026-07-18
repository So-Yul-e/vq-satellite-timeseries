"""YOLOv8 태양광 패널 탐지 모델 다운로드"""
from huggingface_hub import hf_hub_download
import os

# 모델 다운로드
print("YOLOv8 태양광 패널 탐지 모델 다운로드 중...")

model_path = hf_hub_download(
    repo_id="finloop/yolov8s-seg-solar-panels",
    filename="best.pt",
    cache_dir="./models"
)

print(f"✅ 모델 다운로드 완료: {model_path}")

# 심볼릭 링크 생성 (편의성)
target_path = "./models/yolov8_solar_panels.pt"
if os.path.exists(target_path):
    os.remove(target_path)
os.symlink(model_path, target_path)
print(f"✅ 심볼릭 링크 생성: {target_path}")
