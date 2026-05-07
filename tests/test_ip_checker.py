import os
import tempfile
from unittest.mock import patch, MagicMock
from app.ip_checker import IPChecker


class TestIPChecker:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ip_file = os.path.join(self.tmpdir, "current_ip.txt")
        self.checker = IPChecker(ip_file=self.ip_file)

    def test_get_current_ip_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "当前 IP：1.2.3.4 来自：中国"

        with patch("app.ip_checker.requests.get", return_value=mock_response):
            ip = self.checker.get_current_ip()
        assert ip == "1.2.3.4"

    def test_get_current_ip_all_fail(self):
        with patch("app.ip_checker.requests.get", side_effect=Exception("timeout")):
            ip = self.checker.get_current_ip()
        assert ip is None

    def test_check_ip_changed_first_run(self):
        assert self.checker.check_ip_changed("1.2.3.4") is True

    def test_check_ip_not_changed(self):
        self.checker.save_ip("1.2.3.4")
        assert self.checker.check_ip_changed("1.2.3.4") is False

    def test_check_ip_changed(self):
        self.checker.save_ip("1.2.3.4")
        assert self.checker.check_ip_changed("5.6.7.8") is True

    def test_save_and_load_ip(self):
        self.checker.save_ip("1.2.3.4")
        with open(self.ip_file) as f:
            assert f.read() == "1.2.3.4"