from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import verify_password, create_access_token
from app.models.user import User
from pydantic import EmailStr

# 주의: 이 파일은 `from __future__ import annotations`를 의도적으로 사용하지 않는다.
# slowapi의 @limiter.limit() 데코레이터(functools.wraps 기반)와 결합 시
# FastAPI 0.104.1의 get_typed_signature()가 forward-ref annotation을
# 잘못된 globalns에서 evaluate하려다 TypeError로 임포트 자체가 실패하는
# 알려진 상충이 있다 (Depends() 콜러블 기본값이 있는 파라미터에서 재현됨).
# 프로젝트 표준(파일 최상단 future import)에서 벗어나는 예외 — rate limit
# 도입에 따른 불가피한 최소 우회이며, 다른 라우터 파일에는 영향 없다.

router = APIRouter()


@router.post("/login")
@limiter.limit("30/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """로그인 및 토큰 발급"""
    user = db.query(User).filter(User.email == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다"
        )
    
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


from pydantic import BaseModel

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None

@router.post("/register")
@limiter.limit("30/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    db: Session = Depends(get_db)
):
    """회원가입"""
    from app.core.security import get_password_hash

    # 이메일 중복 확인
    existing_user = db.query(User).filter(User.email == body.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 등록된 이메일입니다"
        )

    # 사용자 생성
    user = User(
        email=body.email,
        password_hash=get_password_hash(body.password),
        full_name=body.full_name,
        role_id=1,  # 일반 사용자
        is_active=True
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "message": "회원가입이 완료되었습니다"
    }


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

@router.post("/forgot-password")
@limiter.limit("30/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """비밀번호 재설정 이메일 발송"""
    from app.core.email import send_reset_password_email

    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        # 보안을 위해 유저가 없어도 성공 메시지 반환 (User Enumeration 방지)
        return {"message": "이메일이 발송되었습니다"}

    # 재설정 토큰 생성 (유효기간 30분)
    reset_token = create_access_token(data={"sub": str(user.id), "type": "reset"}, expires_delta=timedelta(minutes=30))

    # 이메일 발송
    await send_reset_password_email(body.email, reset_token)

    return {"message": "이메일이 발송되었습니다"}


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """비밀번호 재설정"""
    from jose import jwt, JWTError
    from app.core.config import settings
    from app.core.security import get_password_hash
    
    try:
        payload = jwt.decode(request.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        token_type = payload.get("type")
        
        if user_id is None or token_type != "reset":
            raise HTTPException(status_code=400, detail="유효하지 않은 토큰입니다")
            
    except JWTError:
        raise HTTPException(status_code=400, detail="유효하지 않은 토큰입니다")
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
        
    # 비밀번호 변경
    user.password_hash = get_password_hash(request.new_password)
    db.commit()
    
    return {"message": "비밀번호가 성공적으로 변경되었습니다"}
