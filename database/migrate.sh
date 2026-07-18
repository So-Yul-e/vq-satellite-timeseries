#!/bin/bash

# 데이터베이스 마이그레이션 실행 스크립트

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-vqsatellite_db}"
DB_USER="${DB_USER:-vqsatellite}"
DB_PASSWORD="${DB_PASSWORD}"

if [ -z "$DB_PASSWORD" ]; then
    echo "오류: DB_PASSWORD 환경변수가 설정되지 않았습니다. 안전하지 않은 기본값 사용을 금지합니다."
    echo "예: DB_PASSWORD=... ./migrate.sh"
    exit 1
fi

export PGPASSWORD=$DB_PASSWORD

echo "데이터베이스 마이그레이션 시작..."

# 마이그레이션 파일 순서대로 실행
# 정렬을 위해 sort 사용
for migration in $(ls migrations/*.sql | sort); do
    echo "실행 중: $migration"
    cat "$migration" | docker exec -i vq-satellite-db psql -U $DB_USER -d $DB_NAME
    if [ $? -ne 0 ]; then
        echo "오류: $migration 실행 실패"
        exit 1
    fi
done

echo "마이그레이션 완료!"
