-- 011_create_solar_panels.sql의 idx_panels_location(GIST on numeric 컬럼)이
-- btree_gist 확장 없이는 실행 자체가 실패한다 (numeric 타입은 GIST 기본 연산자
-- 클래스가 없음 — PostGIS 도입 검증 중 임시 컨테이너 재현으로 확인, 2026-07-11).
-- 그 결과 011의 idx_panels_location 이후에 나열된
-- idx_panels_status / idx_panels_risk_score / idx_panels_is_legal 인덱스와
-- update_solar_panels_updated_at 트리거가 함께 누락된 환경이 있을 수 있다.
--
-- 신규 설치는 011의 해당 구문을 btree로 교정했으므로 더는 실패하지 않는다.
-- 이 마이그레이션은 옛(깨진) 011을 이미 적용해 인덱스/트리거가 누락된 기존 환경을
-- 복구하기 위해 남겨둔다 — 존재 여부와 무관하게 안전하게(IF NOT EXISTS/DROP+CREATE)
-- 재생성하며, 이미 정상인 환경에서는 아무 것도 바뀌지 않는다.
--
-- idx_panels_location 자체는 021_add_postgis.sql의 idx_solar_panels_geom(geometry
-- 컬럼 기반 GIST)이 대체하므로 여기서 다시 만들지 않는다.

CREATE INDEX IF NOT EXISTS idx_panels_status ON solar_panels(status);
CREATE INDEX IF NOT EXISTS idx_panels_risk_score ON solar_panels(risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_panels_is_legal ON solar_panels(is_legal);

DROP TRIGGER IF EXISTS update_solar_panels_updated_at ON solar_panels;
CREATE TRIGGER update_solar_panels_updated_at BEFORE UPDATE ON solar_panels
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
