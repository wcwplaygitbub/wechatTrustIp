import logging
import time
import requests
from playwright.sync_api import sync_playwright, Page, BrowserContext, Browser

from app.cookie_manager import CookieManager
from app.notifier import Notifier

logger = logging.getLogger(__name__)

WEWORK_LOGIN_URL = "https://work.weixin.qq.com/wework_admin/loginpage_wx?from=myhome"
APP_BASE_URL = "https://work.weixin.qq.com/wework_admin/frame#apps/modApiApp/"

# 页面元素选择器
SELECTOR_CONFIG_BTN = (
    "//div[contains(@class, 'js_show_ipConfig_dialog')]//a[contains(@class, '_mod_card_operationLink') and text()='配置']"
)
SELECTOR_IP_TEXTAREA = "textarea.js_ipConfig_textarea"
SELECTOR_IP_CONFIRM_BTN = ".js_ipConfig_confirmBtn"
SELECTOR_LOGIN_SUCCESS = "#check_corp_info"
SELECTOR_IFRAME = "iframe"
SELECTOR_QRCODE_IMG = "img.qrcode_login_img"


class WeWorkBrowser:
    def __init__(
        self,
        cookie_manager: CookieManager,
        notifier: Notifier,
        headless: bool = True,
        qr_timeout: int = 120,
    ):
        self.cookie_manager = cookie_manager
        self.notifier = notifier
        self.headless = headless
        self.qr_timeout = qr_timeout

        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    def _start_browser(self) -> Page:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless, args=["--lang=zh-CN"]
        )
        self._context = self._browser.new_context()

        cookies = self.cookie_manager.load()
        if cookies:
            self._context.add_cookies(cookies)

        page = self._context.new_page()
        page.goto(WEWORK_LOGIN_URL)
        time.sleep(3)
        return page

    def _close_browser(self):
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.error(f"关闭浏览器异常: {e}")
        finally:
            self._browser = None
            self._context = None
            self._playwright = None

    def _save_current_cookies(self):
        if self._context:
            cookies = self._context.cookies()
            self.cookie_manager.save(cookies)

    def check_login_status(self, page: Page, timeout: int = 5000) -> bool:
        try:
            page.wait_for_selector(SELECTOR_LOGIN_SUCCESS, timeout=timeout)
            logger.info("登录状态有效")
            return True
        except Exception:
            pass

        # 检查是否出现短信验证
        try:
            captcha = page.wait_for_selector(".receive_captcha_panel", timeout=5000)
            if captcha:
                logger.info("需要短信验证，等待 30 秒...")
                time.sleep(30)
        except Exception:
            pass

        return False

    def capture_qrcode(self, page: Page) -> bytes | None:
        try:
            page.wait_for_selector(SELECTOR_IFRAME, timeout=5000)
            iframe_element = page.query_selector(SELECTOR_IFRAME)
            if not iframe_element:
                return None
            frame = iframe_element.content_frame()
            if not frame:
                return None

            qr_element = frame.query_selector(SELECTOR_QRCODE_IMG)
            if not qr_element:
                return None

            qr_url = qr_element.get_attribute("src")
            if not qr_url:
                return None
            if qr_url.startswith("/"):
                qr_url = "https://work.weixin.qq.com" + qr_url

            resp = requests.get(qr_url, timeout=10)
            return resp.content
        except Exception as e:
            logger.error(f"截取二维码失败: {e}")
            return None

    def _wait_for_scan_login(self, page: Page) -> bool:
        """轮询等待用户扫码登录，成功返回 True。
        不能导航走，否则会打断页面上的二维码轮询 JS，导致收不到扫码回调。
        通过检查 URL 变化、iframe 消失或登录元素出现来判断。"""
        interval = 5
        elapsed = 0
        login_url_prefix = "https://work.weixin.qq.com/wework_admin/loginpage_wx"

        while elapsed < self.qr_timeout:
            time.sleep(interval)
            elapsed += interval
            try:
                current_url = page.url
                logger.info(f"等待扫码... ({elapsed}/{self.qr_timeout}s) URL: {current_url}")

                # 情况1：URL 已经跳转离开登录页
                if not current_url.startswith(login_url_prefix):
                    logger.info(f"扫码登录成功（URL 已跳转: {current_url}）")
                    return True

                # 情况2：URL 没变但页面内容变了（登录元素出现）
                try:
                    page.wait_for_selector(SELECTOR_LOGIN_SUCCESS, timeout=2000)
                    logger.info("扫码登录成功（检测到登录元素）")
                    return True
                except Exception:
                    pass

                # 情况3：iframe 消失了（二维码区域不见了，说明页面状态变了）
                iframe_element = page.query_selector(SELECTOR_IFRAME)
                if iframe_element is None:
                    logger.info("扫码登录成功（iframe 已消失）")
                    return True

            except Exception as e:
                logger.warning(f"轮询检查异常: {e}")

        logger.error("扫码超时")
        return False

    def update_trusted_ip(self, page: Page, ip: str, app_ids: list[str]) -> bool:
        all_ok = True
        for app_id in app_ids:
            url = f"{APP_BASE_URL}{app_id}"
            try:
                page.goto(url)
                time.sleep(2)

                btn = page.wait_for_selector(SELECTOR_CONFIG_BTN, timeout=5000)
                btn.click()

                page.wait_for_selector(SELECTOR_IP_TEXTAREA, timeout=5000)
                textarea = page.locator(SELECTOR_IP_TEXTAREA)
                textarea.fill(ip)
                logger.info(f"已输入 IP: {ip} (app: {app_id})")

                confirm = page.locator(SELECTOR_IP_CONFIRM_BTN)
                confirm.click()
                time.sleep(3)

                logger.info(f"应用 {app_id} 可信 IP 更新成功")
            except Exception as e:
                logger.error(f"应用 {app_id} 更新可信 IP 失败: {e}")
                all_ok = False
        return all_ok

    def keep_alive(self) -> bool:
        """Cookie 保活：用已有 Cookie 访问管理后台检查登录态。有效返回 True，失效会通知。"""
        page = None
        try:
            page = self._start_browser()
            if self.check_login_status(page):
                self._save_current_cookies()
                logger.info("Cookie 保活成功")
                return True

            logger.info("Cookie 已失效，推送二维码通知")
            return self._handle_expired_cookie(page)
        except Exception as e:
            logger.error(f"Cookie 保活异常: {e}")
            self.notifier.send_text(f"Cookie 保活异常: {e}")
            return False
        finally:
            self._close_browser()

    def _handle_expired_cookie(self, page: Page) -> bool:
        """处理 Cookie 失效：截图 → 通知 → 等待扫码 → 保存新 Cookie"""
        qr_data = self.capture_qrcode(page)
        if not qr_data:
            self.notifier.send_text("Cookie 已失效但未能获取登录二维码，请手动处理")
            return False

        self.notifier.send_image_with_text(qr_data, "企业微信 Cookie 已失效，请扫码登录")
        logger.info("二维码已推送，等待扫码...")

        if self._wait_for_scan_login(page):
            self._save_current_cookies()
            self.notifier.send_text("扫码登录成功，Cookie 已更新")
            return True
        else:
            self.notifier.send_text("扫码超时，下次定时任务将重试")
            return False

    def run_update_flow(self, ip: str, app_ids: list[str]) -> bool:
        """完整更新流程：启动浏览器 → 检查登录态 → 修改 IP 或通知扫码"""
        page = None
        try:
            page = self._start_browser()

            if self.check_login_status(page):
                ok = self.update_trusted_ip(page, ip, app_ids)
                if ok:
                    self._save_current_cookies()
                    self.notifier.send_text(f"可信 IP 已更新为: {ip}")
                else:
                    self.notifier.send_text(f"可信 IP 更新部分失败，IP: {ip}")
                return ok

            logger.info("Cookie 无效，需要重新登录")
            if not self._handle_expired_cookie(page):
                return False

            ok = self.update_trusted_ip(page, ip, app_ids)
            if ok:
                self.notifier.send_text(f"扫码登录后，可信 IP 已更新为: {ip}")
            else:
                self.notifier.send_text(f"登录成功但 IP 更新失败，IP: {ip}")
            return ok

        except Exception as e:
            logger.error(f"更新流程异常: {e}")
            self.notifier.send_text(f"更新可信 IP 失败: {e}")
            return False
        finally:
            self._close_browser()
