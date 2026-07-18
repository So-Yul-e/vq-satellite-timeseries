"""테스트: 전남 해남 1개 지역만 스캔"""
import sys
sys.path.insert(0, '/app')

from detect_solar_panels import *

if __name__ == "__main__":
    print("="*60)
    print("🧪 테스트: 전남 해남 지역 스캔")
    print("="*60)

    # 1. GEE 초기화
    print("\n1️⃣ Google Earth Engine 초기화...")
    if not init_gee():
        print("❌ GEE 초기화 실패.")
        print("💡 GEE 인증이 필요합니다:")
        print("   1. earthengine authenticate")
        print("   2. 또는 서비스 계정 키 제공")
        sys.exit(1)

    # 2. YOLOv8 모델 로드
    print("\n2️⃣ YOLOv8 모델 로드...")
    model_path = "./models/yolov8_solar_panels.pt"
    if not os.path.exists(model_path):
        print(f"❌ 모델 파일 없음: {model_path}")
        sys.exit(1)

    model = YOLO(model_path)
    print(f"✅ 모델 로드 완료")

    # 3. 데이터베이스 연결
    print("\n3️⃣ 데이터베이스 연결...")
    try:
        conn = get_db_connection()
        print("✅ DB 연결 성공")
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        sys.exit(1)

    # 4. 전남 해남 스캔
    print("\n4️⃣ 전남 해남 스캔 시작...")
    print("="*60)

    count = scan_region(
        "전남 해남",
        34.5700,
        126.5900,
        model,
        conn
    )

    print("="*60)
    print(f"✅ 테스트 완료! 탐지 개수: {count}")
    print("="*60)

    conn.close()
