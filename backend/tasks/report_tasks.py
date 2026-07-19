from celery_app import celery_app


@celery_app.task
def send_report_run(report_run_id: str):
    pass
