from app.core.celery_app import celery_app

@celery_app.task
def run_clustering(satellite_id: str):
    return {"status": "completed", "satellite_id": satellite_id}
