import logging
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve(path):
    # Anchor relative log paths to this package's directory rather than the
    # process's cwd, which depends on how/where the process was launched.
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


class ConsoleColorFormatter(logging.Formatter):
    RED = "\033[31m"
    RESET = "\033[0m"

    def format(self, record):
        message = super().format(record)
        if record.levelno >= logging.ERROR and self._use_color():
            return f"{self.RED}{message}{self.RESET}"
        return message

    def _use_color(self):
        return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


_file_formatter = logging.Formatter(
    fmt='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def setup_root_logger():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ConsoleColorFormatter(
        fmt='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s',
        datefmt='%H:%M:%S'
    ))
    root_logger.addHandler(console_handler)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


_task_console_formatter = ConsoleColorFormatter(
    fmt='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    datefmt='%H:%M:%S'
)


def reset_task_logs(*log_files):
    # Called once from the scheduler entrypoint; setup_task_logger always appends so that
    # other processes lazily importing a task module (e.g. the admin "trigger task" button)
    # don't wipe out logs the scheduler already wrote this run.
    os.makedirs(os.path.join(BASE_DIR, 'logs'), exist_ok=True)
    for log_file in log_files:
        open(_resolve(log_file), 'w', encoding='utf-8').close()


def setup_task_logger(name, log_file):
    os.makedirs(os.path.join(BASE_DIR, 'logs'), exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False

    file_handler = logging.FileHandler(_resolve(log_file), mode='a', encoding='utf-8')
    file_handler.setFormatter(_file_formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(_task_console_formatter)
    logger.addHandler(console_handler)

    return logger
