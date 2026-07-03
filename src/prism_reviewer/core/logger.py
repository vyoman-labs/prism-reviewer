import logging
import sys
from datetime import datetime

class MillisecondFormatter(logging.Formatter):
    """
    Formatter that includes millisecond precision timestamps.
    Example: 2023-01-01 12:00:00.123 - prism_reviewer.agents.warden - INFO - Message
    """
    default_time_format = "%Y-%m-%d %H:%M:%S.%f"

    def formatTime(self, record, datefmt=None):
        ct = datetime.fromtimestamp(record.created)
        s = ct.strftime(self.default_time_format)[:-3]  # Trim to milliseconds
        return s

def get_logger(name: str = "prism_reviewer") -> logging.Logger:
    """
    Returns a configured logger with console output, millisecond timestamps,
    logger name, and clear log level names.

    The %(name)s field in the format string means every log line carries the
    logger name (e.g. prism_reviewer.agents.warden), making parallel agent
    logs grep-able without any additional infrastructure.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        # Logger already configured
        return logger

    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    formatter = MillisecondFormatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    return logger