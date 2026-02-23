import threading
from collections.abc import Callable


def run_in_background(func: Callable[[], None], name: str = 'acms-local-task') -> None:
    thread = threading.Thread(target=func, name=name, daemon=True)
    thread.start()
