-- 태양광 패널 탐지 결과와 허가 데이터 매칭 테이블
DROP TABLE IF EXISTS panel_permit_matches CASCADE;

CREATE TABLE panel_permit_matches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- 관계
    panel_id UUID NOT NULL REFERENCES solar_panels(id) ON DELETE CASCADE,
    permit_id UUID NOT NULL REFERENCES solar_permits(id) ON DELETE CASCADE,

    -- 매칭 정보
    distance_m DECIMAL(10, 2) NOT NULL,  -- 거리(m)
    match_type VARCHAR(20) NOT NULL CHECK (match_type IN ('exact', 'nearby', 'suspected_illegal')),
    match_confidence DECIMAL(5, 4),  -- 매칭 신뢰도 (0-1)

    -- 비교 정보
    area_ratio DECIMAL(5, 2),  -- 면적 비율 (탐지 면적 / 예상 허가 면적)

    -- 매칭 상태
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'rejected')),

    -- 메타 정보
    notes TEXT,  -- 추가 메모
    metadata JSONB,  -- 추가 데이터

    -- 타임스탬프
    matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMP,
    verified_by UUID REFERENCES users(id),

    -- 중복 방지
    CONSTRAINT unique_panel_permit_match UNIQUE (panel_id, permit_id)
);

-- 인덱스
CREATE INDEX idx_panel_permit_matches_panel ON panel_permit_matches(panel_id);
CREATE INDEX idx_panel_permit_matches_permit ON panel_permit_matches(permit_id);
CREATE INDEX idx_panel_permit_matches_type ON panel_permit_matches(match_type);
CREATE INDEX idx_panel_permit_matches_status ON panel_permit_matches(status);
CREATE INDEX idx_panel_permit_matches_distance ON panel_permit_matches(distance_m);

-- 주석
COMMENT ON TABLE panel_permit_matches IS '태양광 패널 탐지 결과와 허가 데이터 매칭 정보';
COMMENT ON COLUMN panel_permit_matches.match_type IS '매칭 유형: exact(정확 일치), nearby(근처), suspected_illegal(무허가 의심)';
COMMENT ON COLUMN panel_permit_matches.match_confidence IS '매칭 신뢰도 (0-1)';
COMMENT ON COLUMN panel_permit_matches.area_ratio IS '탐지 면적 / 예상 허가 면적 비율';
