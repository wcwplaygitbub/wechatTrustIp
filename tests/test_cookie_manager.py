import json
import os
import tempfile
from app.cookie_manager import CookieManager


class TestCookieManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cookie_file = os.path.join(self.tmpdir, "cookies.json")
        self.manager = CookieManager(cookie_file=self.cookie_file)

    def test_save_and_load(self):
        cookies = [
            {"name": "sid", "value": "abc123", "domain": ".work.weixin.qq.com", "path": "/"}
        ]
        self.manager.save(cookies)
        loaded = self.manager.load()
        assert loaded == cookies

    def test_load_no_file(self):
        loaded = self.manager.load()
        assert loaded is None

    def test_clear(self):
        cookies = [{"name": "sid", "value": "abc123", "domain": ".work.weixin.qq.com", "path": "/"}]
        self.manager.save(cookies)
        assert os.path.exists(self.cookie_file)
        self.manager.clear()
        assert not os.path.exists(self.cookie_file)

    def test_clear_no_file(self):
        self.manager.clear()  # 不应报错
        assert not os.path.exists(self.cookie_file)