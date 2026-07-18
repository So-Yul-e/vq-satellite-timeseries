from typing import List
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from app.core.config import settings
from pydantic import EmailStr

conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=settings.USE_CREDENTIALS,
    VALIDATE_CERTS=settings.VALIDATE_CERTS,
    SUPPRESS_SEND=settings.MAIL_SUPPRESS_SEND,
)

async def send_reset_password_email(email_to: EmailStr, token: str):
    """
    비밀번호 재설정 이메일 발송
    """
    reset_link = f"http://localhost:3000/reset-password?token={token}"
    
    html = f"""
    <html>
        <body style="margin: 0; padding: 0; box-sizing: border-box; font-family: Arial, Helvetica, sans-serif;">
        <div style="width: 100%; background: #efefef; border-radius: 10px; padding: 10px;">
          <div style="margin: 0 auto; width: 90%; text-align: center;">
            <h1 style="background-color: #005FA8; padding: 5px 10px; border-radius: 5px; color: white;">비밀번호 재설정 요청</h1>
            <div style="margin: 30px auto; background: white; width: 40%; border-radius: 10px; padding: 50px; text-align: center;">
              <h3 style="margin-bottom: 100px; font-size: 24px;">안녕하세요!</h3>
              <p style="margin-bottom: 30px;">아래 버튼을 클릭하여 비밀번호를 재설정하세요.</p>
              <a style="display: block; margin: 0 auto; border: none; background-color: #005FA8; color: white; width: 50%; line-height: 50px; text-decoration: none; border-radius: 10px;" href="{reset_link}">
                비밀번호 재설정
              </a>
              <p style="margin-top: 50px;">만약 본인이 요청하지 않았다면 이 이메일을 무시하세요.</p>
            </div>
          </div>
        </div>
        </body>
    </html>
    """

    message = MessageSchema(
        subject="[VQ Satellite] 비밀번호 재설정",
        recipients=[email_to],
        body=html,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    
    # SUPPRESS_SEND가 True면 실제 전송 대신 로그에 출력됨 (FastMail 내부 동작)
    await fm.send_message(message)
    
    # 개발 편의를 위해 콘솔에도 링크 출력
    if settings.MAIL_SUPPRESS_SEND:
        print(f"==================================================")
        print(f" [EMAIL DEBUG] To: {email_to}")
        print(f" [EMAIL DEBUG] Link: {reset_link}")
        print(f"==================================================")
