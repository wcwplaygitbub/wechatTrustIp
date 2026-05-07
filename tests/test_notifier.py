import base64
from unittest.mock import patch, MagicMock
from app.notifier import Notifier


class TestNotifier:
    def setup_method(self):
        self.notifier = Notifier(webhook_url="https://example.com/webhook?key=test")

    def test_send_text(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}

        with patch("app.notifier.requests.post", return_value=mock_resp) as mock_post:
            result = self.notifier.send_text("hello")
        assert result is True
        call_args = mock_post.call_args
        body = call_args[1]["json"]
        assert body["msgtype"] == "text"
        assert body["text"]["content"] == "hello"

    def test_send_image_with_text(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}

        image_data = b"fake_png_data"
        with patch("app.notifier.requests.post", return_value=mock_resp) as mock_post:
            result = self.notifier.send_image_with_text(image_data, "请扫码登录")
        assert result is True
        # Should have 2 calls: one for image, one for text
        assert mock_post.call_count == 2
        # Check image call
        img_call_args = mock_post.call_args_list[0]
        img_body = img_call_args[1]["json"]
        assert img_body["msgtype"] == "image"
        assert "base64" in img_body["image"]
        assert "md5" in img_body["image"]
        # Check text call
        text_call_args = mock_post.call_args_list[1]
        text_body = text_call_args[1]["json"]
        assert text_body["msgtype"] == "text"
        assert text_body["text"]["content"] == "请扫码登录"

    def test_send_text_failure(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"errcode": 1, "errmsg": "error"}

        with patch("app.notifier.requests.post", return_value=mock_resp):
            result = self.notifier.send_text("hello")
        assert result is False

    def test_send_text_exception(self):
        with patch("app.notifier.requests.post", side_effect=Exception("timeout")):
            result = self.notifier.send_text("hello")
        assert result is False