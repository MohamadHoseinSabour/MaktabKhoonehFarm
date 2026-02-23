from app.tasks.celery_app import celery_app


def celery_worker_available(timeout: float = 0.8) -> bool:
    """Best-effort check for at least one reachable Celery worker."""
    try:
        inspector = celery_app.control.inspect(timeout=timeout)
        if not inspector:
            return False
        return bool(inspector.ping())
    except Exception:
        return False
