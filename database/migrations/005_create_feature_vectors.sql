-- Feature Vectors 테이블 생성
CREATE TABLE IF NOT EXISTS feature_vectors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    satellite_id UUID NOT NULL REFERENCES satellites(id) ON DELETE CASCADE,
    codebook_id UUID REFERENCES vq_codebooks(id) ON DELETE SET NULL,
    vector_index INTEGER NOT NULL,
    vector_data BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX idx_vectors_satellite_id ON feature_vectors(satellite_id);
CREATE INDEX idx_vectors_codebook_id ON feature_vectors(codebook_id);
CREATE INDEX idx_vectors_satellite_index ON feature_vectors(satellite_id, vector_index);

-- 복합 인덱스 (공간 쿼리 최적화)
CREATE INDEX idx_vectors_lookup ON feature_vectors(satellite_id, vector_index, codebook_id);
