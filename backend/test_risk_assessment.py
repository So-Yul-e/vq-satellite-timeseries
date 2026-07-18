import sys
import os
import asyncio
from datetime import datetime
from uuid import uuid4
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Load .env file explicitly
# Go up one level from 'backend' if necessary, or check current dir
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
if os.path.exists(env_path):
    print(f"ℹ️  Loading .env from: {env_path}")
    load_dotenv(env_path)
else:
    print(f"⚠️  .env file not found at: {env_path}")

# Add backend to path so we can import app modules
sys.path.append(os.getcwd())

from app.core.database import SessionLocal, engine, Base
from app.models.solar_panel import SolarPanel
from app.models.risk_assessment import RiskAssessment
from app.services.risk_assessment_service import RiskAssessmentService
from app.core.config import settings

# Rest of the file remains same...

def create_dummy_panel(db):
    # Check if any panel exists
    try:
        panel = db.query(SolarPanel).first()
        if panel:
            print(f"ℹ️  Using existing panel: {panel.id}")
            return panel
    except Exception:
        pass # Table might not exist yet
    
    print("ℹ️  Creating a dummy solar panel for testing...")
    # Create a dummy panel (Bukhansan like location)
    panel = SolarPanel(
        id=uuid4(),
        latitude=37.659,
        longitude=126.975,
        address="Bukhansan Test Area",
        status="detected",
        detection_date=datetime.now(),
        confidence_score=0.95,
        is_illegal=True,
        metadata_json={"area_m2": 1500.0} # Simulate 1500m2 size
    )
    db.add(panel)
    db.commit()
    db.refresh(panel)
    return panel

def main():
    print(f"Checking DB Connection...")
    db_url = str(settings.DATABASE_URL)
    
    # Mask password for log
    if ":" in db_url and "@" in db_url:
        part1 = db_url.split("@")[0]
        site = db_url.split("@")[1]
        part1_masked = part1.split(":")[0] + ":****" 
        print(f"ℹ️  Target DB: {part1_masked}@{site}")
        
        # Additional Warning
        if "user:password" in db_url:
             print("⚠️  WARNING: It seems you are using the DEFAULT Pydantic value (user:password).")
             print("   This means .env was NOT loaded correctly or DATABASE_URL is missing in .env.")
    
    # Try connecting
    try:
        # Create tables
        Base.metadata.create_all(bind=engine)
        print("✅ DB Connection & Tables Verified!")
    except Exception as e:
        print(f"❌ DB Init Failed: {e}")
        return

    db = SessionLocal()
    try:
        print("🚀 Starting Risk Assessment Simulation...")
        
        # 1. Prepare Data
        panel = create_dummy_panel(db)
        
        # 2. Run Service
        service = RiskAssessmentService(db)
        print(f"\nrunning assess_panel_risk for panel {panel.id}...")
        
        assessment = service.assess_panel_risk(panel.id)
        
        print("\n✅ Assessment Coming Through! (Here is the result)")
        print("-" * 40)
        print(f"🏷️  Risk Level: {assessment.risk_level.upper()}")
        print(f"💯 Total Score: {assessment.total_risk_score}/100")
        print("-" * 40)
        print(f"⛰️  Slope Risk: {assessment.slope_risk_score} (Degree: {assessment.slope_degree})")
        print(f"🌲 Forest Risk: {assessment.forest_risk_score} (Damage: {assessment.forest_damage_area_m2}m²)")
        print(f"💧 Water Risk:  {assessment.water_risk_score}")
        print(f"🚫 Protected:   {'Yes' if assessment.protected_area_violation else 'No'}")
        print("-" * 40)
        
        print("\n[Analysis]")
        if assessment.slope_risk_score <= 20: 
            print("👉 Mountain API result seems default (Low slope) - Likely API Failed or Flat area.")
        else:
            print("👉 Mountain API worked! Higher slope detected.")
            
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()
