-- field_inspections 테이블 생성
CREATE TABLE IF NOT EXISTS field_inspections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    panel_id UUID NOT NULL REFERENCES solar_panels(id) ON DELETE RESTRICT,
    inspector_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    inspection_date DATE NOT NULL,
    inspection_status VARCHAR(20) DEFAULT 'scheduled' CHECK (inspection_status IN ('scheduled', 'in_progress', 'completed', 'cancelled')),
    is_illegal_confirmed BOOLEAN,
    violation_types JSONB,
    photos JSONB,
    notes TEXT,
    gps_coordinates JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX idx_inspections_panel ON field_inspections(panel_id);
CREATE INDEX idx_inspections_inspector ON field_inspections(inspector_id);
CREATE INDEX idx_inspections_status ON field_inspections(inspection_status);
CREATE INDEX idx_inspections_date ON field_inspections(inspection_date);
