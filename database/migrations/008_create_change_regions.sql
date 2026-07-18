-- Change Regions 테이블 생성
CREATE TABLE IF NOT EXISTS change_regions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    detection_id UUID NOT NULL REFERENCES change_detections(id) ON DELETE CASCADE,
    polygon_coords JSONB NOT NULL,
    area_m2 DECIMAL(12,2),
    change_type VARCHAR(50),
    confidence DECIMAL(5,4) CHECK (confidence >= 0.0 AND confidence <= 1.0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX idx_regions_detection_id ON change_regions(detection_id);
CREATE INDEX idx_regions_change_type ON change_regions(change_type);
CREATE INDEX idx_regions_polygon ON change_regions USING GIN(polygon_coords);
