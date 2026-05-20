import os
import threading
import time
from types import SimpleNamespace

import app.console as console
from app.scheduler import TaskScheduler


class FakeIPChecker:
    def __init__(self):
        self.saved_ip = None

    def get_current_ip(self):
        return "1.2.3.4"

    def check_ip_changed(self, ip):
        return True

    def load_ip(self):
        return "5.6.7.8"

    def save_ip(self, ip):
        self.saved_ip = ip


class FakeNotifier:
    def send_text(self, content):
        return True


class FakeEventStore:
    def __init__(self):
        self.events = []

    def add(self, *args, **kwargs):
        self.events.append((args, kwargs))

    def get_last_update_time(self):
        return None

    def get_app_statuses(self):
        return {}

    def get_events(self, limit=5):
        return []


class SuccessfulBrowser:
    def run_update_flow(self, ip, app_ids):
        return True


class BlockingBrowser:
    def __init__(self):
        self.started = threading.Event()
        self.second_call_started = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()
        self._active = 0

    def run_update_flow(self, ip, app_ids):
        with self._lock:
            self._active += 1
            if self._active == 1:
                self.started.set()
            else:
                self.second_call_started.set()
        try:
            self.release.wait(timeout=2)
            return True
        finally:
            with self._lock:
                self._active -= 1


class FakeStatusScheduler:
    last_ip = "1.2.3.4"

    def get_next_check_time(self):
        return None


class FakeStatusIPChecker:
    def load_ip(self):
        return "1.2.3.4"


def test_status_reports_qrcode_while_login_flow_is_waiting(tmp_path, monkeypatch):
    qrcode_file = tmp_path / "qrcode.png"
    qrcode_file.write_bytes(b"png")
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text("[]")

    monkeypatch.setattr(
        console,
        "settings",
        SimpleNamespace(
            data_dir=str(tmp_path),
            cookie_file=str(cookie_file),
            wework_app_ids=["app-1"],
        ),
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                scheduler=FakeStatusScheduler(),
                ip_checker=FakeStatusIPChecker(),
                event_store=FakeEventStore(),
                started_at=time.time(),
            )
        )
    )

    status = console.console_status(request, user="admin")

    assert status["has_qrcode"] is True


def test_trigger_check_updates_scheduler_status_and_events_on_success():
    ip_checker = FakeIPChecker()
    event_store = FakeEventStore()
    scheduler = TaskScheduler(
        ip_checker=ip_checker,
        browser=SuccessfulBrowser(),
        notifier=FakeNotifier(),
        event_store=event_store,
        app_ids=["app-1"],
        ip_check_cron="*/10 * * * *",
        keep_alive_interval_minutes=20,
    )

    try:
        result = scheduler.trigger_check()
    finally:
        scheduler.shutdown()

    assert result == {"status": "ok", "message": "IP 已更新", "ip": "1.2.3.4"}
    assert ip_checker.saved_ip == "1.2.3.4"
    assert scheduler.last_ip == "1.2.3.4"
    assert event_store.events[-1][0][0] == "ip_update"
    assert event_store.events[-1][0][2] == "success"


def test_scheduled_ip_check_is_serialized_with_manual_jobs():
    browser = BlockingBrowser()
    scheduler = TaskScheduler(
        ip_checker=FakeIPChecker(),
        browser=browser,
        notifier=FakeNotifier(),
        event_store=FakeEventStore(),
        app_ids=["app-1"],
        ip_check_cron="*/10 * * * *",
        keep_alive_interval_minutes=20,
    )
    scheduler._add_ip_check_job()
    job = scheduler._scheduler.get_jobs()[0]

    try:
        scheduler.submit_force_update()
        assert browser.started.wait(timeout=1)

        scheduled_thread = threading.Thread(target=job.func)
        scheduled_thread.start()
        time.sleep(0.1)

        assert not browser.second_call_started.is_set()
    finally:
        browser.release.set()
        scheduled_thread.join(timeout=1)
        scheduler.shutdown()
