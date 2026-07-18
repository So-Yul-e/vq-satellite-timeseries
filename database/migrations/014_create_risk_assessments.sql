-- risk_assessments 테이블 생성
CREATE TABLE IF NOT EXISTS risk_assessments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    panel_id UUID NOT NULL REFERENCES solar_panels(id) ON DELETE CASCADE,
    slope_degree DECIMAL(5,2),
    slope_risk_score INTEGER CHECK (slope_risk_score >= 0 AND slope_risk_score <= 100),
    forest_damage_area_m2 DECIMAL(12,2),
    forest_risk_score INTEGER CHECK (forest_risk_score >= 0 AND forest_risk_score <= 100),
    water_distance_m DECIMAL(10,2),
    water_risk_score INTEGER CHECK (water_risk_score >= 0 AND water_risk_score <= 100),
    protected_area_violation BOOLEAN,
    protected_risk_score INTEGER CHECK (protected_risk_score >= 0 AND protected_risk_score <= 100),
    total_risk_score INTEGER CHECK (total_risk_score >= 0 AND total_risk_score <= 100),
    risk_level VARCHAR(20) CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    assessment_date TIMESTAMP DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX idx_risk_panel_id ON risk_assessments(panel_id);
CREATE INDEX idx_risk_total_score ON risk_assessments(total_risk_score DESC);
CREATE INDEX idx_risk_level ON risk_assessments(risk_level);
