-- panel_permits 테이블 생성
CREATE TABLE IF NOT EXISTS panel_permits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    panel_id UUID NOT NULL REFERENCES solar_panels(id) ON DELETE CASCADE,
    permit_id UUID NOT NULL REFERENCES permits(id) ON DELETE CASCADE,
    match_type VARCHAR(20) NOT NULL CHECK (match_type IN ('exact', 'overlap', 'nearby')),
    overlap_ratio DECIMAL(5,4),
    distance_m DECIMAL(10,2),
    match_confidence DECIMAL(5,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_panel_permit UNIQUE (panel_id, permit_id)
);

-- 인덱스 생성
CREATE INDEX idx_panel_permits_panel ON panel_permits(panel_id);
CREATE INDEX idx_panel_permits_permit ON panel_permits(permit_id);
