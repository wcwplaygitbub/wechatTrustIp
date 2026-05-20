import logging
from concurrent.futures import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.ip_checker import IPChecker
from app.browser import WeWorkBrowser
from app.notifier import Notifier
from app.event_store import EventStore

logger = logging.getLogger(__name__)


class TaskScheduler:
    def __init__(
        self,
        ip_checker: IPChecker,
        browser: WeWorkBrowser,
        notifier: Notifier,
        event_store: EventStore,
        app_ids: list[str],
        ip_check_cron: str,
        keep_alive_interval_minutes: int,
    ):
        self.ip_checker = ip_checker
        self.browser = browser
        self.notifier = notifier
        self.event_store = event_store
        self.app_ids = app_ids
        self.ip_check_cron = ip_check_cron
        self.keep_alive_interval_minutes = keep_alive_interval_minutes
        self._scheduler = BackgroundScheduler()
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._last_ip: str | None = None

    @property
    def last_ip(self) -> str | None:
        return self._last_ip or self.ip_checker.load_ip()

    def start(self):
        self._add_ip_check_job()
        self._scheduler.start()
        logger.info("定时任务调度器已启动")
        self._executor.submit(self._check_ip_job)

    @property
    def running(self) -> bool:
        return self._scheduler.running

    def get_next_check_time(self) -> str | None:
        for job in self._scheduler.get_jobs():
            if "IP 检测" in job.name and job.next_run_time:
                return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
        return None

    def submit_check(self):
        self._executor.submit(self._check_ip_job)

    def submit_force_update(self):
        self._executor.submit(self._force_update_job)

    def reschedule_check(self, cron_expr: str):
        for job in self._scheduler.get_jobs():
            if "IP 检测" in job.name:
                job.reschedule(trigger=CronTrigger.from_crontab(cron_expr))
                break

    def shutdown(self):
        if self._scheduler.running:
            self._scheduler.shutdown()
        self._executor.shutdown(wait=False)
        logger.info("定时任务调度器已停止")

    def _add_ip_check_job(self):
        try:
            self._scheduler.add_job(
                func=self.submit_check,
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
            self.event_store.add("ip_check", "IP 检测失败：获取 IP 失败", "error")
            return

        if not self.ip_checker.check_ip_changed(ip):
            logger.info("IP 未变化，跳过")
            return

        old_ip = self.ip_checker.load_ip()
        logger.info(f"IP 变化，开始更新可信 IP: {ip}")
        self.event_store.add("ip_change", f"IP 变化: {old_ip} -> {ip}", "warning",
                             {"old_ip": old_ip, "new_ip": ip})
        ok = self.browser.run_update_flow(ip, self.app_ids)
        if ok:
            self.ip_checker.save_ip(ip)
            self._last_ip = ip
            self.event_store.add("ip_update", f"可信 IP 更新成功: {ip}", "success",
                                 {"ip": ip})
        else:
            logger.error("可信 IP 更新失败，下次任务将重试")
            self.event_store.add("ip_update", f"可信 IP 更新失败: {ip}", "error",
                                 {"ip": ip})

    def _keep_alive_job(self):
        logger.info("开始 Cookie 保活任务")
        self.browser.keep_alive()

    def _force_update_job(self):
        logger.info("开始强制更新 IP 任务")
        ip = self.ip_checker.get_current_ip()
        if not ip:
            logger.error("强制更新: 获取 IP 失败")
            self.event_store.add("force_update", "强制更新失败：获取 IP 失败", "error")
            return
        ok = self.browser.run_update_flow(ip, self.app_ids)
        if ok:
            self.ip_checker.save_ip(ip)
            self._last_ip = ip
            self.notifier.send_text(f"强制更新成功，IP: {ip}")
            self.event_store.add("force_update", f"强制更新成功: {ip}", "success",
                                 {"ip": ip})
        else:
            logger.error("强制更新失败")
            self.notifier.send_text(f"强制更新失败，IP: {ip}")
            self.event_store.add("force_update", f"强制更新失败: {ip}", "error",
                                 {"ip": ip})

    def trigger_check(self) -> dict:
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
            self._last_ip = ip
            self.event_store.add("ip_update", f"可信 IP 更新成功: {ip}", "success",
                                 {"ip": ip})
            return {"status": "ok", "message": "IP 已更新", "ip": ip}
        else:
            self.event_store.add("ip_update", f"可信 IP 更新失败: {ip}", "error",
                                 {"ip": ip})
            return {"status": "error", "message": "IP 更新失败", "ip": ip}
