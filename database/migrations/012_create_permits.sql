-- permits 테이블 생성
CREATE TABLE IF NOT EXISTS permits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    permit_number VARCHAR(100) UNIQUE NOT NULL,
    permit_type VARCHAR(50) NOT NULL CHECK (permit_type IN ('forest_land_use', 'energy_subsidy', 'building_permit')),
    issuing_authority VARCHAR(100) NOT NULL,
    applicant_name VARCHAR(200),
    permit_area_m2 DECIMAL(12,2),
    permit_polygon JSONB,
    permit_start_date DATE,
    permit_end_date DATE,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'expired', 'revoked')),
    metadata_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_synced_at TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX idx_permits_number ON permits(permit_number);
CREATE INDEX idx_permits_type ON permits(permit_type);
CREATE INDEX idx_permits_polygon ON permits USING GIN(permit_polygon);
CREATE INDEX idx_permits_status ON permits(status);

-- updated_at 트리거
CREATE TRIGGER update_permits_updated_at BEFORE UPDATE ON permits
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
