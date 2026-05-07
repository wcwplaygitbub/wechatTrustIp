import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.config import settings
from app.cookie_manager import CookieManager
from app.ip_checker import IPChecker
from app.notifier import Notifier
from app.browser import WeWorkBrowser
from app.scheduler import TaskScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 初始化组件
cookie_manager = CookieManager(cookie_file=settings.cookie_file)
ip_checker = IPChecker(ip_file=settings.ip_file)
notifier = Notifier(webhook_url=settings.wework_webhook_url)
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
    app_ids=settings.wework_app_ids,
    ip_check_cron=settings.ip_check_cron,
    keep_alive_interval_minutes=settings.keep_alive_interval_minutes,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("服务启动中...")
    scheduler.start()
    logger.info("服务已启动")
    yield
    scheduler.shutdown()
    logger.info("服务已停止")


app = FastAPI(title="企业微信可信IP自动更新服务", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/trigger")
def trigger():
    result = scheduler.trigger_check()
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