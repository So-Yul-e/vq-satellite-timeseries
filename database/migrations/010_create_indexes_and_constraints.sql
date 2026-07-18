-- 추가 인덱스 및 제약조건

-- Full-text 검색 인덱스 (향후 확장용)
-- CREATE INDEX idx_satellites_fts ON satellites USING GIN(to_tsvector('english', metadata_json::text));

-- 통계 정보 업데이트
ANALYZE;
