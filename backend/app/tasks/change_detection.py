from app.core.celery_app import celery_app

@celery_app.task
def detect_changes(baseline_id: str, compare_id: str):
    return {"status": "completed", "baseline": baseline_id, "compare": compare_id}
