-- solar_permits/solar_panels의 geom이 위경도와 자동 동기화되도록 트리거를 만든다.
-- 배경: 021이 마이그레이션 시점의 기존 행만 backfill했기 때문에, 이후 INSERT되는
-- 행(예: 허가 데이터 임포트 스크립트)은 geom이 NULL로 남아 PostGIS 매칭에서
-- 조회되지 않는 문제가 있었다 (2026-07-12 확인). 애플리케이션이 geom을 직접
-- 넣으면 그 값을 존중하고, 비어 있을 때만 위경도로 채운다.

CREATE OR REPLACE FUNCTION sync_geom_from_latlng()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.geom IS NULL AND NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
        NEW.geom := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sync_panel_geom_from_center()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.geom IS NULL AND NEW.center_latitude IS NOT NULL AND NEW.center_longitude IS NOT NULL THEN
        NEW.geom := ST_SetSRID(ST_MakePoint(NEW.center_longitude, NEW.center_latitude), 4326);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_solar_permits_geom ON solar_permits;
CREATE TRIGGER trg_solar_permits_geom
    BEFORE INSERT OR UPDATE ON solar_permits
    FOR EACH ROW EXECUTE FUNCTION sync_geom_from_latlng();

DROP TRIGGER IF EXISTS trg_solar_panels_geom ON solar_panels;
CREATE TRIGGER trg_solar_panels_geom
    BEFORE INSERT OR UPDATE ON solar_panels
    FOR EACH ROW EXECUTE FUNCTION sync_panel_geom_from_center();

-- 기존 행 backfill (021 이후 들어온 행 대상)
UPDATE solar_permits
SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
WHERE geom IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL;

UPDATE solar_panels
SET geom = ST_SetSRID(ST_MakePoint(center_longitude, center_latitude), 4326)
WHERE geom IS NULL AND center_latitude IS NOT NULL AND center_longitude IS NOT NULL;
