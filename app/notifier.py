import base64
import hashlib
import logging
import requests

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_text(self, content: str) -> bool:
        payload = {
            "msgtype": "text",
            "text": {"content": content},
        }
        return self._post(payload)

    def send_image_with_text(self, image_bytes: bytes, text: str = "") -> bool:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        md5 = hashlib.md5(image_bytes).hexdigest()

        # 先发送图片
        payload = {
            "msgtype": "image",
            "image": {
                "base64": b64,
                "md5": md5,
            },
        }
        img_ok = self._post(payload)

        # 如果有附加文字，再发一条文本
        if text:
            self.send_text(text)

        return img_ok

    def _post(self, payload: dict) -> bool:
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            data = resp.json()
            if data.get("errcode") == 0:
                logger.info(f"通知发送成功: {payload['msgtype']}")
                return True
            else:
                logger.error(f"通知发送失败: {data}")
                return False
        except Exception as e:
            logger.error(f"通知发送异常: {e}")
            return False