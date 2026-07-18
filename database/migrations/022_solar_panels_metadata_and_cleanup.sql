-- solar_panels: metadata_json 컬럼 추가 (risk_assessment_service.py, solar_panels_api.py에서
-- 이미 참조 중이던 컬럼 — 모델에 없어 즉사 버그였던 부분을 스키마에 반영)
ALTER TABLE solar_panels ADD COLUMN IF NOT EXISTS metadata_json JSONB;

-- solar_panels.permit_id: panel_permit_matches FK와 의미 중복되는 비정규 필드 제거
-- (VERSION.md 2026-07-11 확정 결정 — 06_system-architecture.md 참조)
ALTER TABLE solar_panels DROP COLUMN IF EXISTS permit_id;
