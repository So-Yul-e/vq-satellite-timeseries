-- Roles 테이블 생성
CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Image Types 테이블 생성
CREATE TABLE IF NOT EXISTS image_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    code VARCHAR(20) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 기본 데이터 삽입
INSERT INTO roles (name, description) VALUES
    ('user', '일반 사용자'),
    ('admin', '시스템 관리자')
ON CONFLICT (name) DO NOTHING;

INSERT INTO image_types (name, code, description) VALUES
    ('RGB', 'RGB', 'Red-Green-Blue 컬러 영상'),
    ('Multispectral', 'MULTI', '다중 분광 영상'),
    ('Hyperspectral', 'HYPER', '초분광 영상')
ON CONFLICT (code) DO NOTHING;
