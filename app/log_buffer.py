import logging
import re
from collections import deque
from datetime import datetime


_LOG_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+\[(\w+)\]\s+([^:]+):\s+(.*)'
)


class LogBuffer(logging.Handler):
    """内存日志环形缓冲区，启动时从日志文件恢复历史"""

    def __init__(self, maxlen: int = 500):
        super().__init__()
        self._buffer: deque = deque(maxlen=maxlen)

    def load_from_file(self, log_file: str, max_lines: int = 500):
        """服务启动时从日志文件加载历史记录"""
        try:
            with open(log_file) as f:
                lines = f.readlines()
        except FileNotFoundError:
            return

        for line in lines[-max_lines:]:
            m = _LOG_PATTERN.match(line.strip())
            if not m:
                continue
            time_str, level, module, message = m.groups()
            try:
                ts = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").timestamp()
            except ValueError:
                ts = 0
            self._buffer.append({
                "time": time_str,
                "ts": ts,
                "level": level,
                "module": module,
                "message": message,
            })

    def emit(self, record: logging.LogRecord):
        try:
            self._buffer.append({
                "time": datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S"),
                "ts": record.created,
                "level": record.levelname,
                "module": record.name,
                "message": self.format(record),
            })
        except Exception:
            pass

    def get_entries(self, after: float = 0, level: str | None = None,
                    page: int = 1, page_size: int = 50) -> dict:
        """返回分页日志。最新在前。返回 {entries, total, page, page_size}。"""
        entries = list(reversed(self._buffer))
        if after:
            entries = [e for e in entries if e["ts"] > after]
        if level and level != "ALL":
            entries = [e for e in entries if e["level"] == level]

        total = len(entries)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "entries": entries[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def clear(self):
        self._buffer.clear()


log_buffer = LogBuffer()
