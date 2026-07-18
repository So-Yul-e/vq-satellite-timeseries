-- Change Detections 테이블 생성
CREATE TABLE IF NOT EXISTS change_detections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    baseline_sat_id UUID NOT NULL REFERENCES satellites(id) ON DELETE RESTRICT,
    compare_sat_id UUID NOT NULL REFERENCES satellites(id) ON DELETE RESTRICT,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    change_mask_path VARCHAR(500),
    change_area_km2 DECIMAL(12,4),
    change_type VARCHAR(50),
    parameters_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    CONSTRAINT different_satellites CHECK (baseline_sat_id != compare_sat_id)
);

-- 인덱스 생성
CREATE INDEX idx_detections_user_id ON change_detections(user_id);
CREATE INDEX idx_detections_baseline ON change_detections(baseline_sat_id);
CREATE INDEX idx_detections_compare ON change_detections(compare_sat_id);
CREATE INDEX idx_detections_status ON change_detections(status);
CREATE INDEX idx_detections_created ON change_detections(created_at);
