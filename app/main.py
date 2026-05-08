import logging
import os
import time
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.config import settings
from app.cookie_manager import CookieManager
from app.ip_checker import IPChecker
from app.notifier import Notifier
from app.browser import WeWorkBrowser
from app.scheduler import TaskScheduler
from app.log_buffer import log_buffer
from app.event_store import EventStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 内存日志缓冲区
logging.getLogger().addHandler(log_buffer)

# 文件日志（按大小轮转）
file_handler = RotatingFileHandler(
    settings.log_file,
    maxBytes=settings.log_file_max_mb * 1024 * 1024,
    backupCount=settings.log_file_backup_count,
    encoding="utf-8",
)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger().addHandler(file_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("服务启动中...")

    cookie_manager = CookieManager(cookie_file=settings.cookie_file)
    ip_checker = IPChecker(ip_file=settings.ip_file)
    notifier = Notifier(webhook_url=settings.wework_webhook_url)
    event_store = EventStore(data_dir=settings.data_dir)
    browser = WeWorkBrowser(
        cookie_manager=cookie_manager,
        notifier=notifier,
        headless=settings.headless,
        qr_timeout=settings.qr_timeout_seconds,
    )
    scheduler = TaskScheduler(
        ip_checker=ip_checker,
        browser=browser,
        notifier=notifier,
        event_store=event_store,
        app_ids=settings.wework_app_ids,
        ip_check_cron=settings.ip_check_cron,
        keep_alive_interval_minutes=settings.keep_alive_interval_minutes,
    )

    app.state.ip_checker = ip_checker
    app.state.browser = browser
    app.state.notifier = notifier
    app.state.event_store = event_store
    app.state.scheduler = scheduler
    app.state.started_at = time.time()

    scheduler.start()

    # 从日志文件恢复历史记录到内存缓冲区
    log_buffer.load_from_file(settings.log_file)

    logger.info("服务已启动")
    yield
    scheduler.shutdown()
    logger.info("服务已停止")


app = FastAPI(title="企业微信可信IP自动更新服务", lifespan=lifespan)

from app.console import router as console_router, register_auth_handler
app.include_router(console_router)
register_auth_handler(app)


@app.get("/")
def root():
    return RedirectResponse(url="/console/")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/trigger")
def trigger():
    result = app.state.scheduler.trigger_check()
    return result


@app.get("/status")
def status():
    saved_ip = None
    try:
        with open(settings.ip_file) as f:
            saved_ip = f.read().strip()
    except FileNotFoundError:
        pass

    has_cookie = os.path.exists(settings.cookie_file)

    return {
        "current_ip": saved_ip,
        "has_cookie": has_cookie,
        "app_ids": settings.wework_app_ids,
    }


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=False)
