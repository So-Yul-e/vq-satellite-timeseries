-- 관리자 계정 생성 (비밀번호: admin123, 해시는 실제로는 애플리케이션에서 생성)
-- 이 예제는 개발용이므로 실제 운영에서는 제거해야 함

-- 기본 관리자 계정 (password_hash는 'admin123'의 bcrypt 해시)
-- 실제 해시는 애플리케이션에서 생성되어야 함
-- INSERT INTO users (email, password_hash, full_name, role_id) VALUES
--     ('admin@example.com', '$2b$12$...', 'System Admin', 2)
-- ON CONFLICT (email) DO NOTHING;
