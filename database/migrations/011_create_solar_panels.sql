-- solar_panels 테이블 생성
CREATE TABLE IF NOT EXISTS solar_panels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    satellite_id UUID NOT NULL REFERENCES satellites(id) ON DELETE CASCADE,
    detection_job_id UUID REFERENCES jobs(id),
    panel_polygon JSONB NOT NULL,
    center_latitude DECIMAL(10,7) NOT NULL,
    center_longitude DECIMAL(10,7) NOT NULL,
    area_m2 DECIMAL(12,2) NOT NULL,
    estimated_capacity_kw DECIMAL(10,2),
    installation_date_estimated DATE,
    detection_confidence DECIMAL(5,4) CHECK (detection_confidence >= 0.0 AND detection_confidence <= 1.0),
    is_legal BOOLEAN,
    permit_id VARCHAR(100),
    risk_score INTEGER CHECK (risk_score >= 0 AND risk_score <= 100),
    status VARCHAR(20) DEFAULT 'detected' CHECK (status IN ('detected', 'verified', 'illegal_confirmed', 'legal_confirmed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX idx_panels_satellite_id ON solar_panels(satellite_id);
-- 위경도(numeric)에는 btree 인덱스를 쓴다. 실제 공간 매칭은 021이 추가하는
-- geometry 컬럼(geom)의 GIST 인덱스로 수행한다 (numeric 컬럼에 GIST는 불가).
CREATE INDEX idx_panels_location ON solar_panels(center_latitude, center_longitude);
CREATE INDEX idx_panels_status ON solar_panels(status);
CREATE INDEX idx_panels_risk_score ON solar_panels(risk_score DESC);
CREATE INDEX idx_panels_is_legal ON solar_panels(is_legal);

-- updated_at 트리거
CREATE TRIGGER update_solar_panels_updated_at BEFORE UPDATE ON solar_panels
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
