import threading
import functools

_task_locks = {
    'task_update_battle_logs':  threading.RLock(),
    'task_update_ranked_weeks': threading.RLock(),
    'task_update_clan_members': threading.RLock(),
    'task_update_raid_weekend': threading.RLock(),
    'task_update_clan_war':     threading.RLock(),
    'task_update_cwl':          threading.RLock(),
}


def task_lock(logger):
    """Decorator factory: skips and logs if the task is already running in another thread."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            lock = _task_locks.get(fn.__name__)
            if lock is None:
                return fn(*args, **kwargs)
            if not lock.acquire(blocking=False):
                logger.warning(f'{fn.__name__} skipped — already running in another thread.')
                return
            try:
                return fn(*args, **kwargs)
            finally:
                lock.release()
        return wrapper
    return decorator
