"""
패널-허가 매칭 서비스(PanelPermitMatchingService) 테스트

PostGIS(ST_DWithin/ST_Distance) 기반 근접 매칭을 검증한다. PostGIS 확장이 있는
PostgreSQL 연결이 필요하므로, 접속 가능한 DB가 없으면 모듈 전체를 skip한다.

로컬에서 격리 검증하려면 임시 postgis 컨테이너를 띄우고 마이그레이션
001~024를 순서대로 적용한 뒤 아래처럼 실행한다:

    docker run -d --name pg-test -p 5555:5432 \
        -e POSTGRES_PASSWORD=test -e POSTGRES_USER=test -e POSTGRES_DB=test \
        postgis/postgis:15-3.4-alpine
    PGPASSWORD=test psql -h localhost -p 5555 -U test -d test \
        -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'
    for f in database/migrations/*.sql; do
        PGPASSWORD=test psql -h localhost -p 5555 -U test -d test -f "$f"
    done
    TEST_DATABASE_URL=postgresql://test:test@localhost:5555/test \
        pytest backend/tests/test_panel_permit_matching.py -v
    docker rm -f pg-test
"""
import os
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import Base
from app.models.role import Role
from app.models.user import User
from app.models.satellite import Satellite
from app.models.solar_panel import SolarPanel
from app.models.solar_permit import SolarPermit
from app.models.panel_permit_match import PanelPermitMatch
from app.services.panel_permit_matching_service import PanelPermitMatchingService


def _resolve_test_database_url():
    """전용 테스트 DB(TEST_DATABASE_URL)만 사용한다.

    settings.DATABASE_URL 폴백은 의도적으로 제거 — 개발 공유 DB에 테스트
    행이 쌓이고, 같은 폴백을 쓰던 test_risk_assessment의 drop_all teardown과
    조합되면 실데이터 전체가 드랍될 수 있었다(2026-07-18 실제 근접 사고).
    """
    return os.environ.get("TEST_DATABASE_URL")


def _postgis_available(url: str) -> bool:
    if not url:
        return False
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT PostGIS_Version()"))
        engine.dispose()
        return True
    except Exception:
        return False


_TEST_DB_URL = _resolve_test_database_url()
_HAS_POSTGIS = _postgis_available(_TEST_DB_URL)

pytestmark = pytest.mark.skipif(
    not _HAS_POSTGIS,
    reason="전용 테스트 DB가 필요합니다 (TEST_DATABASE_URL 설정 — 모듈 docstring의 postgis 컨테이너 절차 참조)",
)


@pytest.fixture(scope="module")
def db_session():
    engine = create_engine(_TEST_DB_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="module")
def seed_satellite(db_session):
    """매칭 테스트용 role -> user -> satellite 시드."""
    role = db_session.query(Role).filter(Role.name == "matching_test_role").first()
    if not role:
        role = Role(name="matching_test_role", description="panel-permit matching test role")
        db_session.add(role)
        db_session.commit()
        db_session.refresh(role)

    user = User(
        email=f"matching-test-{uuid.uuid4()}@example.com",
        password_hash="test_hash",
        full_name="Matching Test User",
        role_id=role.id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    satellite = Satellite(user_id=user.id, file_path="/tmp/matching_test_satellite.tif")
    db_session.add(satellite)
    db_session.commit()
    db_session.refresh(satellite)

    return satellite


def _make_panel(db_session, satellite, lat: float, lon: float, area_m2: float = 1000.0) -> SolarPanel:
    panel = SolarPanel(
        satellite_id=satellite.id,
        center_latitude=lat,
        center_longitude=lon,
        panel_polygon={"type": "Point", "coordinates": [lon, lat]},
        area_m2=area_m2,
        detection_confidence=0.9,
        status="detected",
    )
    db_session.add(panel)
    db_session.commit()
    db_session.refresh(panel)
    # geom은 021 마이그레이션에서 기존 데이터 backfill용 UPDATE로 채워지는 컬럼이라
    # ORM insert만으로는 채워지지 않는다 - 테스트에서도 동일하게 명시적으로 세팅한다.
    db_session.execute(
        text(
            "UPDATE solar_panels SET geom = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) "
            "WHERE id = :id"
        ),
        {"lon": lon, "lat": lat, "id": str(panel.id)},
    )
    db_session.commit()
    db_session.refresh(panel)
    return panel


def _make_permit(db_session, name: str, lat: float, lon: float, capacity_kw: float = 100.0) -> SolarPermit:
    permit = SolarPermit(
        facility_name=name,
        latitude=lat,
        longitude=lon,
        capacity=capacity_kw,
    )
    db_session.add(permit)
    db_session.commit()
    db_session.refresh(permit)
    db_session.execute(
        text(
            "UPDATE solar_permits SET geom = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) "
            "WHERE id = :id"
        ),
        {"lon": lon, "lat": lat, "id": str(permit.id)},
    )
    db_session.commit()
    db_session.refresh(permit)
    return permit


class TestFindNearbyPermits:
    """ST_DWithin/ST_Distance 기반 근접 허가 검색"""

    def test_finds_permit_within_radius(self, db_session, seed_satellite):
        # 다른 테스트의 잔여 데이터와 겹치지 않는 좌표를 사용 (module-scope DB 재사용)
        panel = _make_panel(db_session, seed_satellite, 37.4010, 127.1010)
        permit = _make_permit(db_session, "인근 발전소 단독", 37.4015, 127.1015)

        service = PanelPermitMatchingService(db_session)
        results = service.find_nearby_permits(panel, radius_km=0.2)

        assert len(results) == 1
        found_permit, distance_m = results[0]
        assert found_permit.id == permit.id
        # Haversine 근사 약 71m 안팎 - 넉넉한 허용범위로 검증
        assert 0 < distance_m < 200

    def test_excludes_permit_outside_radius(self, db_session, seed_satellite):
        # 부산 근방 패널 - 서울 허가와 매칭되면 안 됨
        panel = _make_panel(db_session, seed_satellite, 35.1796, 129.0756)

        service = PanelPermitMatchingService(db_session)
        results = service.find_nearby_permits(panel, radius_km=2.0)

        assert results == []

    def test_results_sorted_by_distance(self, db_session, seed_satellite):
        panel = _make_panel(db_session, seed_satellite, 36.5000, 127.5000)
        far_permit = _make_permit(db_session, "먼 발전소", 36.5150, 127.5150)  # ~약 1.9km
        near_permit = _make_permit(db_session, "가까운 발전소", 36.5010, 127.5010)  # ~약 130m

        service = PanelPermitMatchingService(db_session)
        results = service.find_nearby_permits(panel, radius_km=5.0)

        result_ids = [permit.id for permit, _ in results]
        assert result_ids.index(near_permit.id) < result_ids.index(far_permit.id)


class TestMatchPanelWithPermits:
    """매칭 유형(exact/nearby/suspected_illegal) 판정"""

    def test_exact_match_within_100m(self, db_session, seed_satellite):
        panel = _make_panel(db_session, seed_satellite, 33.4996, 126.5312)
        _make_permit(db_session, "제주 발전소", 33.4997, 126.5313)

        service = PanelPermitMatchingService(db_session)
        result = service.match_panel_with_permits(panel)

        assert result["match_type"] == "exact"
        assert result["is_illegal"] is False

    def test_suspected_illegal_when_no_permit_nearby(self, db_session, seed_satellite):
        panel = _make_panel(db_session, seed_satellite, 38.0, 128.0)

        service = PanelPermitMatchingService(db_session)
        result = service.match_panel_with_permits(panel)

        assert result["match_type"] == "suspected_illegal"
        assert result["is_illegal"] is True
        assert result["nearest_permit_distance_m"] is None


class TestMatchCoordinatesWithPermits:
    """SolarPanel row 없이 좌표만으로 매칭 (/api/solar/analyze 경로)"""

    def test_matches_by_coordinates_without_panel_row(self, db_session, seed_satellite):
        _make_permit(db_session, "좌표 매칭 발전소", 35.8714, 128.6014)

        service = PanelPermitMatchingService(db_session)
        result = service.match_coordinates_with_permits(
            latitude=35.8714, longitude=128.6014, area_m2=500, radius_m=200
        )

        assert result["has_permit"] is True
        assert result["is_legal"] is True

    def test_no_match_returns_suspected_illegal(self, db_session, seed_satellite):
        service = PanelPermitMatchingService(db_session)
        result = service.match_coordinates_with_permits(
            latitude=39.0, longitude=125.0, area_m2=500, radius_m=100
        )

        assert result["has_permit"] is False
        assert result["match_type"] == "suspected_illegal"


class TestSaveMatchResult:
    """upsert(on_conflict_do_update) 동작 검증"""

    def test_upsert_creates_then_updates(self, db_session, seed_satellite):
        panel = _make_panel(db_session, seed_satellite, 37.0, 127.0)
        permit = _make_permit(db_session, "upsert 발전소", 37.0005, 127.0005)

        service = PanelPermitMatchingService(db_session)
        service.save_match_result(
            panel_id=panel.id, permit_id=permit.id,
            distance_m=50.0, match_type="exact", match_confidence=0.95,
        )

        match = db_session.query(PanelPermitMatch).filter(
            PanelPermitMatch.panel_id == panel.id,
            PanelPermitMatch.permit_id == permit.id,
        ).first()
        assert match is not None
        assert float(match.distance_m) == 50.0

        # 동일 (panel_id, permit_id)로 재호출 시 UNIQUE 제약 위반 없이 갱신되어야 함
        service.save_match_result(
            panel_id=panel.id, permit_id=permit.id,
            distance_m=80.0, match_type="nearby", match_confidence=0.7,
        )

        db_session.refresh(match)
        assert float(match.distance_m) == 80.0
        assert match.match_type == "nearby"

        count = db_session.query(PanelPermitMatch).filter(
            PanelPermitMatch.panel_id == panel.id,
            PanelPermitMatch.permit_id == permit.id,
        ).count()
        assert count == 1
