import logging
from collections import deque
from datetime import datetime


class LogBuffer(logging.Handler):
    """内存日志环形缓冲区，保留最近 200 条日志"""

    def __init__(self, maxlen: int = 200):
        super().__init__()
        self._buffer: deque = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord):
        try:
            self._buffer.append({
                "time": datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S"),
                "level": record.levelname,
                "module": record.name,
                "message": self.format(record),
            })
        except Exception:
            pass

    def get_entries(self) -> list[dict]:
        """返回所有日志条目，最新在前"""
        return list(reversed(self._buffer))

    def clear(self):
        self._buffer.clear()


log_buffer = LogBuffer()
