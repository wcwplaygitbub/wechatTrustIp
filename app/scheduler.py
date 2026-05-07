import logging
from concurrent.futures import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.ip_checker import IPChecker
from app.browser import WeWorkBrowser
from app.notifier import Notifier

logger = logging.getLogger(__name__)


class TaskScheduler:
    def __init__(
        self,
        ip_checker: IPChecker,
        browser: WeWorkBrowser,
        notifier: Notifier,
        app_ids: list[str],
        ip_check_cron: str,
        keep_alive_interval_minutes: int,
    ):
        self.ip_checker = ip_checker
        self.browser = browser
        self.notifier = notifier
        self.app_ids = app_ids
        self.ip_check_cron = ip_check_cron
        self.keep_alive_interval_minutes = keep_alive_interval_minutes
        self._scheduler = BackgroundScheduler()
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._last_ip: str | None = None

    def start(self):
        self._add_ip_check_job()
        # 不再注册 Cookie 保活任务：企业微信 Web 管理后台会话互斥，
        # 保活操作本身会淘汰当前会话导致 Cookie 失效。
        # Cookie 只在 IP 检测时顺带检查，失效则触发扫码流程。
        self._scheduler.start()
        logger.info("定时任务调度器已启动")

        # 启动时在线程中立即执行一次 IP 检测（避免在 asyncio 事件循环中直接跑 Playwright）
        self._executor.submit(self._check_ip_job)

    def shutdown(self):
        if self._scheduler.running:
            self._scheduler.shutdown()
        self._executor.shutdown(wait=False)
        logger.info("定时任务调度器已停止")

    def _add_ip_check_job(self):
        try:
            self._scheduler.add_job(
                func=self._check_ip_job,
                trigger=CronTrigger.from_crontab(self.ip_check_cron),
                name="IP 检测",
            )
            logger.info(f"IP 检测任务已注册: {self.ip_check_cron}")
        except Exception as e:
            logger.error(f"IP 检测任务注册失败: {e}")

    def _add_keep_alive_job(self):
        try:
            self._scheduler.add_job(
                func=self._keep_alive_job,
                trigger=IntervalTrigger(minutes=self.keep_alive_interval_minutes),
                name="Cookie 保活",
            )
            logger.info(f"Cookie 保活任务已注册: 每 {self.keep_alive_interval_minutes} 分钟")
        except Exception as e:
            logger.error(f"Cookie 保活任务注册失败: {e}")

    def _check_ip_job(self):
        logger.info("开始 IP 检测任务")
        ip = self.ip_checker.get_current_ip()
        if not ip:
            logger.error("IP 检测任务: 获取 IP 失败，跳过")
            return

        if not self.ip_checker.check_ip_changed(ip):
            logger.info("IP 未变化，跳过")
            return

        logger.info(f"IP 变化，开始更新可信 IP: {ip}")
        ok = self.browser.run_update_flow(ip, self.app_ids)
        if ok:
            self.ip_checker.save_ip(ip)
            self._last_ip = ip
        else:
            logger.error("可信 IP 更新失败，下次任务将重试")

    def _keep_alive_job(self):
        logger.info("开始 Cookie 保活任务")
        self.browser.keep_alive()

    def _force_update_job(self):
        """强制更新 IP（不管是否变化）"""
        logger.info("开始强制更新 IP 任务")
        ip = self.ip_checker.get_current_ip()
        if not ip:
            logger.error("强制更新: 获取 IP 失败")
            return
        ok = self.browser.run_update_flow(ip, self.app_ids)
        if ok:
            self.ip_checker.save_ip(ip)
            self._last_ip = ip
            self.notifier.send_text(f"强制更新成功，IP: {ip}")
        else:
            logger.error("强制更新失败")
            self.notifier.send_text(f"强制更新失败，IP: {ip}")

    def trigger_check(self) -> dict:
        """手动触发一次 IP 检测，返回结果摘要"""
        ip = self.ip_checker.get_current_ip()
        if not ip:
            return {"status": "error", "message": "获取 IP 失败"}

        changed = self.ip_checker.check_ip_changed(ip)
        if not changed:
            return {"status": "ok", "message": "IP 未变化", "ip": ip}

        future = self._executor.submit(self.browser.run_update_flow, ip, self.app_ids)
        ok = future.result()
        if ok:
            self.ip_checker.save_ip(ip)
            return {"status": "ok", "message": "IP 已更新", "ip": ip}
        else:
            return {"status": "error", "message": "IP 更新失败", "ip": ip}