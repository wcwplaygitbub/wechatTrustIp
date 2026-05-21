import logging
import os
import time
import requests
from playwright.sync_api import sync_playwright, Page, BrowserContext, Browser

from app.cookie_manager import CookieManager
from app.notifier import Notifier

logger = logging.getLogger(__name__)

WEWORK_LOGIN_URL = "https://work.weixin.qq.com/wework_admin/loginpage_wx?from=myhome"
WEWORK_HOME_URL = "https://work.weixin.qq.com/wework_admin/frame"
APP_BASE_URL = "https://work.weixin.qq.com/wework_admin/frame#apps/modApiApp/"

BROWSER_ARGS = [
    "--lang=zh-CN",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

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
        event_store=None,
    ):
        self.cookie_manager = cookie_manager
        self.notifier = notifier
        self.headless = headless
        self.qr_timeout = qr_timeout
        self.event_store = event_store

        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    @property
    def data_dir(self) -> str:
        return os.path.dirname(self.cookie_manager.cookie_file)

    @property
    def qrcode_file(self) -> str:
        return os.path.join(self.data_dir, "qrcode.png")

    @property
    def captcha_file(self) -> str:
        return os.path.join(self.data_dir, "captcha_code.txt")

    @property
    def captcha_flag_file(self) -> str:
        return os.path.join(self.data_dir, "captcha_needed.txt")

    def _new_context(self) -> BrowserContext:
        return self._browser.new_context(
            user_agent=USER_AGENT,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )

    def _start_browser(self) -> Page:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless, args=BROWSER_ARGS
        )
        self._context = self._new_context()

        cookies = self.cookie_manager.load()
        if cookies:
            self._context.add_cookies(cookies)

        page = self._context.new_page()
        page.goto(WEWORK_LOGIN_URL)
        time.sleep(3)
        return page

    def _start_browser_to_home(self) -> Page:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless, args=BROWSER_ARGS
        )
        self._context = self._new_context()

        cookies = self.cookie_manager.load()
        if cookies:
            self._context.add_cookies(cookies)

        page = self._context.new_page()
        page.goto(WEWORK_HOME_URL)
        time.sleep(3)
        return page

    def _start_browser_clean(self) -> Page:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless, args=BROWSER_ARGS
        )
        self._context = self._new_context()

        page = self._context.new_page()
        page.goto(WEWORK_LOGIN_URL)
        time.sleep(5)
        return page

    def _close_browser(self):
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.debug(f"关闭浏览器异常: {e}")
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
            return False

    def capture_qrcode(self, page: Page) -> bytes | None:
        try:
            logger.info(f"尝试获取二维码，当前 URL: {page.url}")
            debug_path = os.path.join(self.data_dir, "debug_login.png")
            page.screenshot(path=debug_path)

            page.wait_for_selector(SELECTOR_IFRAME, timeout=10000)
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
        """轮询等待用户扫码登录"""
        interval = 5
        elapsed = 0
        login_url_prefix = "https://work.weixin.qq.com/wework_admin/loginpage_wx"

        while elapsed < self.qr_timeout:
            time.sleep(interval)
            elapsed += interval
            try:
                # 检查 page 是否还活着
                current_url = page.url
                logger.info(f"等待扫码... ({elapsed}/{self.qr_timeout}s)")

                if not current_url.startswith(login_url_prefix):
                    logger.info("扫码登录成功（URL 已跳转）")
                    return True

                try:
                    page.wait_for_selector(SELECTOR_LOGIN_SUCCESS, timeout=2000)
                    logger.info("扫码登录成功（检测到登录元素）")
                    return True
                except Exception:
                    pass

                iframe_element = page.query_selector(SELECTOR_IFRAME)
                if iframe_element is None:
                    logger.info("扫码登录成功（iframe 已消失）")
                    return True

                # 检查是否出现了验证码（扫码后可能弹出）
                if self._has_captcha_on_page(page):
                    logger.info("扫码后出现验证码页面")
                    return True

            except Exception as e:
                # page 被关闭了说明浏览器切换了
                logger.warning(f"轮询检查异常（page 可能已关闭）: {e}")
                return True

        logger.error("扫码超时")
        return False

    def _has_captcha_on_page(self, page: Page) -> bool:
        """检查页面上是否有验证码内容"""
        try:
            body_text = page.inner_text("body")
            return "验证码" in body_text or "短信" in body_text
        except Exception:
            return False

    def _wait_for_captcha(self, timeout: int = 180) -> str | None:
        """轮询等待用户通过控制台输入验证码"""
        for f in [self.captcha_file, self.captcha_flag_file]:
            try:
                os.remove(f)
            except OSError:
                pass

        with open(self.captcha_flag_file, "w") as f:
            f.write(str(int(time.time())))

        # 生成一次性免登录链接
        from app.console import generate_captcha_token
        _, captcha_url = generate_captcha_token()
        self.notifier.send_text(f"需要短信验证码，请点击链接输入: {captcha_url}")

        start = time.time()
        while time.time() - start < timeout:
            time.sleep(1)
            if os.path.exists(self.captcha_file):
                try:
                    with open(self.captcha_file) as f:
                        code = f.read().strip()
                    if code:
                        logger.info(f"收到验证码: {code}")
                        os.remove(self.captcha_file)
                        # 通知前端验证码已处理
                        if self.event_store:
                            self.event_store.add("captcha", "验证码已提交，处理中", "info")
                        return code
                except Exception:
                    pass

        for f in [self.captcha_file, self.captcha_flag_file]:
            try:
                os.remove(f)
            except OSError:
                pass
        logger.error("等待验证码超时")
        return None

    def _fill_captcha_code(self, page: Page, code: str) -> bool:
        """在页面上填入验证码，支持多种页面结构"""
        # 先检查主页面，再检查 iframe
        targets = [page]
        try:
            for iframe_el in page.query_selector_all("iframe"):
                frame = iframe_el.content_frame()
                if frame:
                    targets.append(frame)
        except Exception:
            pass

        for target in targets:
            try:
                inputs = target.query_selector_all("input")
                visible = []
                for inp in inputs:
                    try:
                        if inp.is_visible():
                            inp_type = (inp.get_attribute("type") or "").lower()
                            if inp_type not in ("hidden", "submit", "button", "checkbox", "radio", "file", "image"):
                                visible.append(inp)
                    except Exception:
                        continue

                logger.info(f"找到 {len(visible)} 个可见输入框")

                if len(visible) >= len(code) and len(visible) <= 10:
                    # 有足够的独立框，逐位输入
                    visible[0].click()
                    time.sleep(0.3)
                    for digit in code:
                        page.keyboard.type(digit, delay=100)
                        time.sleep(0.2)
                    logger.info(f"验证码已逐位输入: {code}")
                    time.sleep(2)
                    return True

                if len(visible) >= 1:
                    # 只找到一个框，也用键盘逐位输入（不要 fill，fill 会把所有数字填到一个框里）
                    visible[0].click()
                    time.sleep(0.3)
                    # 先清空
                    visible[0].fill("")
                    time.sleep(0.2)
                    for digit in code:
                        page.keyboard.type(digit, delay=100)
                        time.sleep(0.2)
                    logger.info(f"验证码已逐位输入（单框模式）: {code}")
                    time.sleep(2)
                    return True

            except Exception as e:
                logger.debug(f"填入验证码异常: {e}")
                continue

        logger.warning("未匹配到验证码输入框")
        return False

    def _detect_and_handle_captcha(self, page: Page) -> bool:
        """检测并处理验证码页面，失败时重发新链接重试"""
        try:
            if not self._has_captcha_on_page(page):
                return False

            logger.info("检测到验证码页面，截图保存")
            page.screenshot(path=os.path.join(self.data_dir, "captcha_screenshot.png"))

            # 通知前端需要输入验证码
            if self.event_store:
                self.event_store.add("captcha", "需要输入短信验证码", "warning")

            max_retries = 3
            for attempt in range(max_retries):
                code = self._wait_for_captcha(timeout=180)
                if not code:
                    self.notifier.send_text("等待验证码超时")
                    return False

                result = self._fill_captcha_code(page, code)
                if result:
                    time.sleep(3)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass

                    # 检查验证码是否真的通过了（页面上不再有验证码提示）
                    if not self._has_captcha_on_page(page):
                        logger.info("验证码验证成功")
                        self.notifier.send_text("验证码验证成功")
                        try:
                            os.remove(self.captcha_flag_file)
                        except OSError:
                            pass
                        return True
                    else:
                        logger.warning(f"验证码填写后页面仍有验证码提示（第 {attempt + 1} 次）")
                else:
                    logger.warning(f"验证码填写失败（第 {attempt + 1} 次）")

                # 验证码填写失败或未通过，发新链接重试
                if attempt < max_retries - 1:
                    from app.console import generate_captcha_token
                    _, captcha_url = generate_captcha_token()
                    self.notifier.send_text(f"验证码错误，请重新输入: {captcha_url}")
                    if self.event_store:
                        self.event_store.add("captcha", "验证码错误，已发送新链接", "warning")

            self.notifier.send_text("验证码多次错误，已放弃")
            return False
        except Exception as e:
            logger.error(f"处理验证码异常: {e}")
            return False

    def read_trusted_ip(self, page: Page, app_id: str) -> str | None:
        """读取企业微信上某个应用当前配置的可信 IP"""
        try:
            url = f"{APP_BASE_URL}{app_id}"
            page.goto(url)
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(2)

            # 检测验证码
            self._detect_and_handle_captcha(page)

            btn = page.wait_for_selector(SELECTOR_CONFIG_BTN, timeout=10000)
            btn.click()

            page.wait_for_selector(SELECTOR_IP_TEXTAREA, timeout=5000)
            textarea = page.locator(SELECTOR_IP_TEXTAREA)
            current_ip = textarea.input_value().strip()

            logger.info(f"读取到应用 {app_id} 当前可信 IP: {current_ip or '(空)'}")
            return current_ip if current_ip else None
        except Exception as e:
            logger.error(f"读取应用 {app_id} 可信 IP 失败: {e}")
            return None

    def startup_check(self, current_ip: str, app_ids: list[str]) -> bool:
        """启动时登录企业微信，检查可信 IP 是否与当前公网 IP 一致"""
        page = None
        try:
            logger.info("启动检查：登录企业微信校验可信 IP")
            page = self._start_browser_to_home()

            if not self.check_login_status(page):
                logger.info("Cookie 无效，尝试扫码登录")
                self._close_browser()
                page = self._start_browser_clean()
                if not self._handle_expired_cookie(page):
                    logger.error("启动检查：登录失败")
                    return False

            # 读取第一个应用的可信 IP 作为代表
            registered_ip = self.read_trusted_ip(page, app_ids[0])

            if registered_ip == current_ip:
                logger.info(f"启动检查：可信 IP 一致 ({current_ip})，无需更新")
                # 同步保存到本地
                self.ip_sync_save(current_ip)
                return True

            logger.info(f"启动检查：可信 IP 不一致 (企业微信: {registered_ip}, 当前: {current_ip})，开始更新")
            ok = self.update_trusted_ip(page, current_ip, app_ids)
            if ok:
                self._save_current_cookies()
                self.notifier.send_text(f"启动检查：可信 IP 已从 {registered_ip} 更新为 {current_ip}")
                self.ip_sync_save(current_ip)
            else:
                self.notifier.send_text(f"启动检查：可信 IP 更新失败 ({registered_ip} -> {current_ip})")
            return ok

        except Exception as e:
            logger.error(f"启动检查异常: {e}")
            return False
        finally:
            self._close_browser()

    def ip_sync_save(self, ip: str):
        """同步保存 IP 到本地（通过 cookie_manager 的文件路径推断 ip_file）"""
        try:
            from app.config import settings
            tmp = settings.ip_file + ".tmp"
            with open(tmp, "w") as f:
                f.write(ip)
            os.replace(tmp, settings.ip_file)
        except Exception as e:
            logger.warning(f"保存 IP 文件失败: {e}")

    def update_trusted_ip(self, page: Page, ip: str, app_ids: list[str]) -> bool:
        all_ok = True
        for app_id in app_ids:
            url = f"{APP_BASE_URL}{app_id}"
            try:
                page.goto(url)
                page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(2)

                debug_path = os.path.join(self.data_dir, f"debug_ip_update_{app_id}.png")
                page.screenshot(path=debug_path)

                # 检测验证码
                self._detect_and_handle_captcha(page)

                btn = page.wait_for_selector(SELECTOR_CONFIG_BTN, timeout=10000)
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
                try:
                    page.screenshot(path=os.path.join(self.data_dir, f"error_ip_update_{app_id}.png"))
                except Exception:
                    pass
                logger.error(f"应用 {app_id} 更新可信 IP 失败: {e}")
                all_ok = False
        return all_ok

    def _handle_verification_popup(self, page: Page) -> bool:
        """处理页面上的确认弹窗"""
        try:
            time.sleep(1)
            confirm_btns = page.query_selector_all("button, a")
            for btn in confirm_btns:
                try:
                    text = btn.inner_text()
                    if "确认" in text or "确定" in text:
                        btn.click()
                        logger.info("点击了确认按钮")
                        time.sleep(2)
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def keep_alive(self) -> bool:
        page = None
        try:
            page = self._start_browser_to_home()
            if self.check_login_status(page):
                self._save_current_cookies()
                logger.info("Cookie 保活成功")
                return True

            logger.info("Cookie 已失效，重新打开登录页")
            self._close_browser()
            page = self._start_browser_clean()
            return self._handle_expired_cookie(page)
        except Exception as e:
            logger.error(f"Cookie 保活异常: {e}")
            self.notifier.send_text(f"Cookie 保活异常: {e}")
            return False
        finally:
            self._close_browser()

    def _handle_expired_cookie(self, page: Page) -> bool:
        qr_data = self.capture_qrcode(page)
        if not qr_data:
            self.notifier.send_text("Cookie 已失效但未能获取登录二维码")
            return False

        try:
            with open(self.qrcode_file, "wb") as f:
                f.write(qr_data)
            logger.info(f"二维码已保存到 {self.qrcode_file}")
        except Exception as e:
            logger.warning(f"保存二维码文件失败: {e}")

        self.notifier.send_image_with_text(qr_data, "企业微信 Cookie 已失效，请扫码登录")
        logger.info("二维码已推送，等待扫码...")

        if self._wait_for_scan_login(page):
            self._save_current_cookies()
            self.notifier.send_text("扫码登录成功，Cookie 已更新")
            logger.info("等待页面稳定...")
            time.sleep(3)

            # 扫码后检查验证码
            self._detect_and_handle_captcha(page)
            time.sleep(2)

            try:
                os.remove(self.qrcode_file)
            except OSError:
                pass
            return True
        else:
            self.notifier.send_text("扫码超时，下次定时任务将重试")
            return False

    def run_update_flow(self, ip: str, app_ids: list[str]) -> bool:
        page = None
        try:
            page = self._start_browser_to_home()

            if self.check_login_status(page):
                ok = self.update_trusted_ip(page, ip, app_ids)
                if ok:
                    self._save_current_cookies()
                    self.notifier.send_text(f"可信 IP 已更新为: {ip}")
                else:
                    self.notifier.send_text(f"可信 IP 更新部分失败，IP: {ip}")
                return ok

            logger.info("Cookie 无效，重新打开登录页")
            self._close_browser()

            page = self._start_browser_clean()
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
