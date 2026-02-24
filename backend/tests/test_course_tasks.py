from types import SimpleNamespace

from app.tasks.course_tasks import _safe_update_state


class DummyTask:
    def __init__(self, task_id):
        self.request = SimpleNamespace(id=task_id)
        self.calls: list[tuple[str, dict]] = []

    def update_state(self, *, state: str, meta: dict):
        self.calls.append((state, meta))


def test_safe_update_state_skips_when_task_id_is_missing():
    task = DummyTask(task_id=None)
    _safe_update_state(task, state='FAILURE', meta={'reason': 'x'})
    assert task.calls == []


def test_safe_update_state_calls_update_when_task_id_exists():
    task = DummyTask(task_id='abc123')
    _safe_update_state(task, state='FAILURE', meta={'reason': 'x'})
    assert task.calls == [('FAILURE', {'reason': 'x'})]
