-- VQ Codebooks 테이블 생성
CREATE TABLE IF NOT EXISTS vq_codebooks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    satellite_id UUID NOT NULL UNIQUE REFERENCES satellites(id) ON DELETE CASCADE,
    codebook_size INTEGER NOT NULL,
    vector_dim INTEGER NOT NULL,
    codebook_data BYTEA,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX idx_codebooks_satellite_id ON vq_codebooks(satellite_id);
