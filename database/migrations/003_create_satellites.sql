-- Satellites 테이블 생성
CREATE TABLE IF NOT EXISTS satellites (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    image_type_id INTEGER REFERENCES image_types(id) ON DELETE RESTRICT,
    file_path VARCHAR(500) NOT NULL,
    file_size BIGINT,
    width INTEGER,
    height INTEGER,
    channels INTEGER,
    capture_date DATE,
    latitude_min DECIMAL(10,7),
    latitude_max DECIMAL(10,7),
    longitude_min DECIMAL(10,7),
    longitude_max DECIMAL(10,7),
    thumbnail_path VARCHAR(500),
    metadata_json JSONB,
    status VARCHAR(20) DEFAULT 'uploaded' CHECK (status IN ('uploaded', 'processing', 'completed', 'failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX idx_satellites_user_id ON satellites(user_id);
CREATE INDEX idx_satellites_capture_date ON satellites(capture_date);
CREATE INDEX idx_satellites_status ON satellites(status);
CREATE INDEX idx_satellites_image_type ON satellites(image_type_id);
CREATE INDEX idx_satellites_metadata ON satellites USING GIN(metadata_json);

-- Bounding Box 인덱스 (공간 쿼리 최적화)
CREATE INDEX idx_satellites_bbox ON satellites(latitude_min, latitude_max, longitude_min, longitude_max);

-- updated_at 트리거
CREATE TRIGGER update_satellites_updated_at BEFORE UPDATE ON satellites
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
