import os
import re
import logging
import tempfile
import requests

logger = logging.getLogger(__name__)

_IP_PATTERN = re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')

_IP_URLS = [
    "https://myip.ipip.net",
    "https://ddns.oray.com/checkip",
    "https://ip.3322.net",
    "https://4.ipw.cn",
]


class IPChecker:
    def __init__(self, ip_file: str):
        self.ip_file = ip_file

    def get_current_ip(self) -> str | None:
        for url in _IP_URLS:
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    match = _IP_PATTERN.search(resp.text)
                    if match:
                        logger.info(f"获取公网 IP 成功 [{url}]: {match.group()}")
                        return match.group()
            except Exception as e:
                logger.warning(f"从 {url} 获取 IP 失败: {e}")
        logger.error("所有 IP 查询源均失败")
        return None

    def check_ip_changed(self, current_ip: str) -> bool:
        saved_ip = self._load_ip()
        if saved_ip is None:
            logger.info("首次运行，需要更新 IP")
            return True
        if current_ip != saved_ip:
            logger.info(f"IP 变化: {saved_ip} -> {current_ip}")
            return True
        return False

    def save_ip(self, ip: str):
        tmp = self.ip_file + ".tmp"
        with open(tmp, "w") as f:
            f.write(ip)
        os.replace(tmp, self.ip_file)
        logger.info(f"已保存 IP: {ip}")

    def load_ip(self) -> str | None:
        try:
            with open(self.ip_file) as f:
                return f.read().strip()
        except FileNotFoundError:
            return None

    def _load_ip(self) -> str | None:
        return self.load_ip()