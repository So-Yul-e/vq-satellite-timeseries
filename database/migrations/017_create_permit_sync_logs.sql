-- permit_sync_logs 테이블 생성
CREATE TABLE IF NOT EXISTS permit_sync_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sync_type VARCHAR(50) NOT NULL CHECK (sync_type IN ('forest_land', 'energy_subsidy', 'building_permit')),
    sync_status VARCHAR(20) NOT NULL CHECK (sync_status IN ('success', 'failed', 'partial')),
    records_synced INTEGER,
    records_failed INTEGER,
    error_message TEXT,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX idx_sync_logs_type ON permit_sync_logs(sync_type);
CREATE INDEX idx_sync_logs_status ON permit_sync_logs(sync_status);
CREATE INDEX idx_sync_logs_started ON permit_sync_logs(started_at DESC);
