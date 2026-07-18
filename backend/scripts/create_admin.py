"""
admin 사용자 생성/승격 헬퍼 스크립트

RBAC(require_role("admin")) 도입에 따라, 최초 admin 계정을 만들 수단이 없어
CLI로 제공한다. roles 테이블에는 001 마이그레이션으로 'admin' role이 이미
시드되어 있다고 가정한다.

사용법:
    # 새 admin 계정 생성
    python scripts/create_admin.py create --email admin@example.com --password <strong-password> --full-name "관리자"

    # 기존 사용자를 admin으로 승격
    python scripts/create_admin.py promote --email existing-user@example.com
"""
from __future__ import annotations

import argparse
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.role import Role
from app.models.user import User


def _get_admin_role(db) -> Role:
    role = db.query(Role).filter(Role.name == "admin").first()
    if role is None:
        raise SystemExit(
            "오류: 'admin' role이 roles 테이블에 없습니다. "
            "database/migrations/001_create_roles_and_image_types.sql 마이그레이션을 먼저 적용하세요."
        )
    return role


def create_admin(email: str, password: str, full_name: str | None) -> None:
    db = SessionLocal()
    try:
        admin_role = _get_admin_role(db)

        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise SystemExit(f"오류: 이메일 '{email}'은 이미 존재합니다. promote를 사용하세요.")

        user = User(
            email=email,
            password_hash=get_password_hash(password),
            full_name=full_name,
            role_id=admin_role.id,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"admin 계정 생성 완료: id={user.id}, email={user.email}")
    finally:
        db.close()


def promote_to_admin(email: str) -> None:
    db = SessionLocal()
    try:
        admin_role = _get_admin_role(db)

        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise SystemExit(f"오류: 이메일 '{email}' 사용자를 찾을 수 없습니다.")

        user.role_id = admin_role.id
        db.commit()
        print(f"'{email}' 사용자를 admin으로 승격했습니다.")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="admin 사용자 생성/승격 헬퍼")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="새 admin 계정 생성")
    create_parser.add_argument("--email", required=True)
    create_parser.add_argument("--password", required=True)
    create_parser.add_argument("--full-name", default=None)

    promote_parser = subparsers.add_parser("promote", help="기존 사용자를 admin으로 승격")
    promote_parser.add_argument("--email", required=True)

    args = parser.parse_args()

    if args.command == "create":
        create_admin(args.email, args.password, args.full_name)
    elif args.command == "promote":
        promote_to_admin(args.email)


if __name__ == "__main__":
    main()
