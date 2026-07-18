-- 026: permit_sync_logs 모델↔테이블 드리프트 교정
--
-- PermitSyncLog 모델(backend/app/models/permit.py)에는 records_updated·source_file
-- 컬럼이 정의돼 있으나 017 마이그레이션이 만든 테이블엔 없어, ORM 전체 SELECT/INSERT가
-- UndefinedColumn(500)으로 실패했다. 주간 동기화 이력 기록(SL-H1)을 켜면서 드러남.
-- 모델을 진실원천으로 삼아 누락 컬럼을 추가한다(둘 다 NULL 허용).

ALTER TABLE permit_sync_logs ADD COLUMN IF NOT EXISTS records_updated VARCHAR;
ALTER TABLE permit_sync_logs ADD COLUMN IF NOT EXISTS source_file VARCHAR(500);

-- CHECK 제약도 실사용과 어긋나 있었다:
--  · sync_type: 017은 forest_land/energy_subsidy/building_permit만 허용 →
--    태양광 허가 동기화가 쓰는 'solar_permit_json'을 거부(모델 주석엔 이미 있음).
--  · sync_status: 017은 success/failed/partial만 허용 → 태스크 시작 시 쓰는
--    'running'을 거부.
-- 두 제약을 실제 쓰는 값 집합으로 교체한다.
ALTER TABLE permit_sync_logs DROP CONSTRAINT IF EXISTS permit_sync_logs_sync_type_check;
ALTER TABLE permit_sync_logs ADD CONSTRAINT permit_sync_logs_sync_type_check
  CHECK (sync_type IN ('forest_land', 'energy_subsidy', 'building_permit', 'solar_permit_json'));

ALTER TABLE permit_sync_logs DROP CONSTRAINT IF EXISTS permit_sync_logs_sync_status_check;
ALTER TABLE permit_sync_logs ADD CONSTRAINT permit_sync_logs_sync_status_check
  CHECK (sync_status IN ('success', 'failed', 'partial', 'running'));
