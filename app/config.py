import os
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # 企微配置
    wework_app_ids: list[str] = []
    wework_webhook_key: str = ""

    # 调度配置
    ip_check_cron: str = "*/10 * * * *"
    keep_alive_interval_minutes: int = 20
    headless: bool = True
    qr_timeout_seconds: int = 120
    port: int = 8000

    # 日志配置
    log_file_max_mb: int = 100
    log_file_backup_count: int = 3

    # 控制台配置
    console_username: str = "admin"
    console_password: str = "admin123"
    console_url: str = "http://localhost:8000/console/"
    console_secret_key: str = ""

    @field_validator("wework_app_ids", mode="before")
    @classmethod
    def parse_app_ids(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, (int, float)):
            return [str(v)]
        if isinstance(v, list):
            return [str(item) for item in v]
        return []

    @property
    def wework_webhook_url(self) -> str:
        return f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={self.wework_webhook_key}"

    @property
    def data_dir(self) -> str:
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

    @property
    def cookie_file(self) -> str:
        return os.path.join(self.data_dir, "cookies.json")

    @property
    def ip_file(self) -> str:
        return os.path.join(self.data_dir, "current_ip.txt")

    @property
    def log_file(self) -> str:
        return os.path.join(self.data_dir, "app.log")

    @property
    def password_hash_file(self) -> str:
        return os.path.join(self.data_dir, "password.hash")

    def model_post_init(self, __context):
        os.makedirs(self.data_dir, exist_ok=True)
        if not self.console_secret_key:
            object.__setattr__(self, "console_secret_key", self.wework_webhook_key)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
