import os
import time
import functools

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # coc_stats/, not coc_stats/tasks/
LOCK_DIR = os.path.join(BASE_DIR, 'locks')
STALE_LOCK_SECONDS = 30 * 60  # treat a lock as abandoned if a crashed process never released it


class TaskBusyError(Exception):
    pass


def _lock_path(name):
    os.makedirs(LOCK_DIR, exist_ok=True)
    return os.path.join(LOCK_DIR, f'{name}.lock')


def task_lock(logger):
    """Decorator factory: skips (raises TaskBusyError) if the task is already running.

    Uses an exclusive lock file rather than an in-memory lock so it works across
    processes — the scheduler and the web app (admin "trigger task" button) run
    as separate OS processes and can't see each other's in-memory state.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            path = _lock_path(fn.__name__)
            try:
                if os.path.exists(path) and time.time() - os.path.getmtime(path) > STALE_LOCK_SECONDS:
                    os.remove(path)
            except OSError:
                pass

            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
            except FileExistsError:
                logger.warning(f'{fn.__name__} skipped — already running.')
                raise TaskBusyError(fn.__name__)

            try:
                return fn(*args, **kwargs)
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass
        return wrapper
    return decorator
