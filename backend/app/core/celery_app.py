from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "vq_satellite",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.vq_tasks",
        "app.tasks.solar_permit_tasks"
    ]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",  # 한국 시간대
    enable_utc=False,
    task_track_started=True,
    task_time_limit=60 * 60,  # 1시간 (데이터 동기화는 시간이 오래 걸릴 수 있음)
    task_soft_time_limit=55 * 60,  # 55분
)

# Celery Beat 주기적 작업 스케줄
celery_app.conf.beat_schedule = {
    # 태양광 허가 데이터 동기화 - 매주 일요일 새벽 3시
    'sync-solar-permits-weekly': {
        'task': 'sync_solar_permits',
        'schedule': crontab(hour=3, minute=0, day_of_week=0),  # 일요일 오전 3시
        'options': {
            'expires': 3600 * 12,  # 12시간 내에 실행되지 않으면 취소
        }
    },
}
