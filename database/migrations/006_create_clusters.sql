-- Clusters 테이블 생성
CREATE TABLE IF NOT EXISTS clusters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    satellite_id UUID NOT NULL REFERENCES satellites(id) ON DELETE CASCADE,
    codebook_id UUID REFERENCES vq_codebooks(id) ON DELETE SET NULL,
    cluster_label INTEGER NOT NULL,
    center_vector BYTEA,
    size INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX idx_clusters_satellite_id ON clusters(satellite_id);
CREATE INDEX idx_clusters_codebook_id ON clusters(codebook_id);
CREATE INDEX idx_clusters_label ON clusters(satellite_id, cluster_label);

-- 고유 제약조건 (한 영상에서 동일 레이블은 하나만)
CREATE UNIQUE INDEX idx_clusters_unique ON clusters(satellite_id, cluster_label);
