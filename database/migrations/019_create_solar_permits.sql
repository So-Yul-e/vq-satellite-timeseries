-- solar_permits 테이블 생성 (공공데이터포털 태양광 발전소 허가 정보)
CREATE TABLE IF NOT EXISTS solar_permits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- 발전소 정보
    facility_name VARCHAR(200) NOT NULL,  -- solarGenFcltNm

    -- 위치 정보
    road_address VARCHAR(500),  -- lctnRoadNmAddr
    lot_address VARCHAR(500),  -- lctnLotnoAddr
    latitude DECIMAL(10, 8),  -- latitude (위도)
    longitude DECIMAL(11, 8),  -- longitude (경도)

    -- 설치 상세 위치 정보
    installation_detail_position VARCHAR(100),  -- instlDtlPstnSeNm

    -- 운영 정보
    operation_status VARCHAR(50),  -- oprtngSttsSeNm (예: 정상가동)

    -- 전기 사양
    capacity DECIMAL(10, 2),  -- capa (용량, kW)
    supply_voltage VARCHAR(20),  -- splyVolt (전압, V)
    frequency VARCHAR(20),  -- freq (주파수, Hz)

    -- 설치 정보
    installation_year VARCHAR(4),  -- instlYr
    installation_area VARCHAR(50),  -- instlArea

    -- 상세 용도
    detail_usage VARCHAR(200),  -- detlsUsg

    -- 허가 정보
    permission_date VARCHAR(20),  -- prmsnYmd
    permission_institution VARCHAR(200),  -- prmsnInst

    -- 기관 정보
    institution_code VARCHAR(20),  -- insttCode
    institution_name VARCHAR(200),  -- insttNm

    -- 메타 정보
    criteria_date VARCHAR(20),  -- crtrYmd (기준일)

    -- 원본 데이터 (JSON 형태로 보관)
    raw_data JSONB,

    -- 타임스탬프
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX idx_solar_permits_facility_name ON solar_permits(facility_name);
CREATE INDEX idx_solar_permits_road_address ON solar_permits(road_address);
CREATE INDEX idx_solar_permits_institution_code ON solar_permits(institution_code);
CREATE INDEX idx_solar_permits_operation_status ON solar_permits(operation_status);

-- 위치 검색을 위한 복합 인덱스
CREATE INDEX idx_solar_permits_location ON solar_permits(latitude, longitude) WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- 용량 검색을 위한 인덱스
CREATE INDEX idx_solar_permits_capacity ON solar_permits(capacity);

-- 설치 연도 검색을 위한 인덱스
CREATE INDEX idx_solar_permits_installation_year ON solar_permits(installation_year);

-- updated_at 트리거 (이미 존재하는 함수 사용)
CREATE TRIGGER update_solar_permits_updated_at BEFORE UPDATE ON solar_permits
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 주석 추가
COMMENT ON TABLE solar_permits IS '공공데이터포털 전국태양광발전소전기사업허가정보 데이터';
COMMENT ON COLUMN solar_permits.facility_name IS '태양광 발전소명';
COMMENT ON COLUMN solar_permits.capacity IS '설비용량(kW)';
COMMENT ON COLUMN solar_permits.operation_status IS '운영상태 (예: 정상가동, 중단 등)';
