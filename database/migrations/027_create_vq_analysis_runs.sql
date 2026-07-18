-- 027: VQ 위치 시계열 분석 실행 이력 (결과 영속화 + 최근 분석 목록)
-- 결과가 새로고침마다 휘발되던 문제 해소. 이미지는 uploads/results/{job_id}에 이미
-- 영속되므로 재표시용 결과 JSON + 목록 요약 컬럼만 저장.

CREATE TABLE IF NOT EXISTS vq_analysis_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    buffer_km DOUBLE PRECISION NOT NULL,
    past_date VARCHAR(20),
    t2_date VARCHAR(20),  -- 실제 T2 시점. "current_date"는 PostgreSQL 예약어라 회피
    season_aligned BOOLEAN DEFAULT FALSE,
    n_total INTEGER,
    n_changed INTEGER,
    change_percentage DOUBLE PRECISION,
    solar_panel_count INTEGER,
    n_solar_patches INTEGER,
    job_id VARCHAR(64),
    result_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vq_runs_created_at ON vq_analysis_runs(created_at DESC);
