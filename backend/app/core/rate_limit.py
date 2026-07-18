"""slowapi Limiter 단일 인스턴스.

main.py와 라우터(auth_simple 등)가 동시에 참조하므로 순환 import를 피하기 위해
별도 모듈로 분리한다. IP 기준(get_remote_address) rate limit — 로그인/회원가입/
비밀번호 재설정 크리덴셜 스터핑 방어용 (REVIEW_REPORT H-1).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
