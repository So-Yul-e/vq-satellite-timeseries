-- administrative_actions 테이블 생성
CREATE TABLE IF NOT EXISTS administrative_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    panel_id UUID NOT NULL REFERENCES solar_panels(id) ON DELETE RESTRICT,
    inspection_id UUID REFERENCES field_inspections(id),
    action_type VARCHAR(50) NOT NULL CHECK (action_type IN ('fine', 'restoration_order', 'subsidy_recovery')),
    action_status VARCHAR(20) DEFAULT 'pending' CHECK (action_status IN ('pending', 'in_progress', 'completed', 'cancelled')),
    fine_amount DECIMAL(15,2),
    subsidy_recovery_amount DECIMAL(15,2),
    restoration_deadline DATE,
    documents JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX idx_actions_panel ON administrative_actions(panel_id);
CREATE INDEX idx_actions_type ON administrative_actions(action_type);
CREATE INDEX idx_actions_status ON administrative_actions(action_status);

-- updated_at 트리거
CREATE TRIGGER update_administrative_actions_updated_at BEFORE UPDATE ON administrative_actions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
