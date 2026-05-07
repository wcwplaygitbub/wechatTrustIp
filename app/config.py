import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self):
        self.wework_app_ids: list[str] = self._parse_list("WEWORK_APP_IDS", required=True)
        self.wework_webhook_key: str = self._get("WEWORK_WEBHOOK_KEY", required=True)
        self.ip_check_cron: str = self._get("IP_CHECK_CRON", default="*/10 * * * *")
        self.keep_alive_interval_minutes: int = int(self._get("KEEP_ALIVE_INTERVAL_MINUTES", default="20"))
        self.headless: bool = self._get("HEADLESS", default="true").lower() == "true"
        self.qr_timeout_seconds: int = int(self._get("QR_TIMEOUT_SECONDS", default="120"))
        self.port: int = int(self._get("PORT", default="8000"))

        self.wework_webhook_url: str = (
            f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={self.wework_webhook_key}"
        )
        self.data_dir: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self.cookie_file: str = os.path.join(self.data_dir, "cookies.json")
        self.ip_file: str = os.path.join(self.data_dir, "current_ip.txt")

        os.makedirs(self.data_dir, exist_ok=True)

    @staticmethod
    def _get(key: str, default: str | None = None, required: bool = False) -> str:
        value = os.getenv(key, default)
        if required and not value:
            raise ValueError(f"环境变量 {key} 未设置，请在 .env 文件中配置")
        return value or ""

    @staticmethod
    def _parse_list(key: str, required: bool = False) -> list[str]:
        raw = os.getenv(key, "")
        if required and not raw:
            raise ValueError(f"环境变量 {key} 未设置，请在 .env 文件中配置")
        return [item.strip() for item in raw.split(",") if item.strip()]


settings = Settings()