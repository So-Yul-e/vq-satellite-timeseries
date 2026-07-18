-- PostGIS 확장 도입 (VERSION.md 2026-07-11 확정 결정)
-- 공간 매칭 O(N×M)을 GIST 인덱스 + ST_DWithin으로 해결

CREATE EXTENSION IF NOT EXISTS postgis;

-- solar_panels: geometry 컬럼 추가 + 기존 위경도 컬럼에서 backfill
ALTER TABLE solar_panels ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326);

UPDATE solar_panels
SET geom = ST_SetSRID(ST_MakePoint(center_longitude, center_latitude), 4326)
WHERE center_latitude IS NOT NULL AND center_longitude IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_solar_panels_geom ON solar_panels USING GIST (geom);

-- solar_permits: geometry 컬럼 추가 + 기존 위경도 컬럼에서 backfill
ALTER TABLE solar_permits ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326);

UPDATE solar_permits
SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_solar_permits_geom ON solar_permits USING GIST (geom);

-- 기존 center_latitude/center_longitude, solar_permits.latitude/longitude 컬럼은
-- 하위 호환을 위해 삭제하지 않고 유지한다.
