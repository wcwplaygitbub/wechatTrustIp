import json
import os
import threading
import asyncio
from datetime import datetime
from collections import deque


class EventStore:
    """轻量事件存储，记录 IP 变更、更新结果等关键事件"""

    def __init__(self, data_dir: str, max_events: int = 200):
        self._file = os.path.join(data_dir, "events.json")
        self._max = max_events
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._subscribers: list[asyncio.Queue] = []
        self._load()

    def _load(self):
        try:
            with open(self._file) as f:
                self._events = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._events = []

    def _save(self):
        tmp = self._file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._events[-self._max:], f, ensure_ascii=False)
        os.replace(tmp, self._file)

    def add(self, event_type: str, message: str, level: str = "info", extra: dict | None = None):
        with self._lock:
            entry = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "type": event_type,
                "level": level,
                "message": message,
            }
            if extra:
                entry.update(extra)
            self._events.append(entry)
            if len(self._events) > self._max:
                self._events = self._events[-self._max:]
            self._save()
        # 通知所有 SSE 订阅者
        self._notify(entry)

    def _notify(self, entry: dict):
        """将事件放入所有订阅者的队列"""
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(entry)
            except Exception:
                dead.append(q)
        for q in dead:
            self._subscribers.remove(q)

    def subscribe(self) -> asyncio.Queue:
        """注册一个 SSE 订阅者，返回事件队列"""
        q = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        """取消订阅"""
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def get_events(self, limit: int = 20) -> list[dict]:
        return list(reversed(self._events[-limit:]))

    def get_last_update_time(self) -> str | None:
        for e in reversed(self._events):
            if e.get("type") in ("ip_update", "force_update") and e.get("level") == "success":
                return e["time"]
        return None

    def get_app_statuses(self) -> dict[str, dict]:
        """获取每个 app 的最近一次更新状态"""
        result = {}
        for e in reversed(self._events):
            app_id = e.get("app_id")
            if app_id and app_id not in result:
                result[app_id] = {
                    "app_id": app_id,
                    "success": e.get("level") == "success",
                    "time": e["time"],
                    "message": e.get("message", ""),
                }
        return result
