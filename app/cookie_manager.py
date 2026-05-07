import json
import os
import logging

logger = logging.getLogger(__name__)


class CookieManager:
    def __init__(self, cookie_file: str):
        self.cookie_file = cookie_file

    def save(self, cookies: list[dict]):
        os.makedirs(os.path.dirname(self.cookie_file), exist_ok=True)
        with open(self.cookie_file, "w") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        logger.info(f"Cookie 已保存到 {self.cookie_file}")

    def load(self) -> list[dict] | None:
        try:
            with open(self.cookie_file) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def clear(self):
        try:
            os.remove(self.cookie_file)
            logger.info("Cookie 文件已清除")
        except FileNotFoundError:
            pass