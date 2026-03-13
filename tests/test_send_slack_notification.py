"""
tests/test_send_slack_notification.py

測試 send_slack_notification.py 中的純函式。
執行：uv run pytest tests/
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from send_slack_notification import build_message, format_date_display


# ─── format_date_display ──────────────────────────────────────────────────────

class TestFormatDateDisplay:
    def test_basic(self):
        assert format_date_display("20260313") == "2026/03/13"

    def test_different_date(self):
        assert format_date_display("20260101") == "2026/01/01"


# ─── build_message ────────────────────────────────────────────────────────────

class TestBuildMessage:
    def test_yesterday_prefix(self):
        yesterday = date.today() - timedelta(days=1)
        date_str = yesterday.strftime("%Y%m%d")
        msg = build_message("Data內會", date_str, "https://doc.url", "Drive/path")
        assert msg.startswith("昨天的 Data內會")

    def test_non_yesterday_uses_date(self):
        msg = build_message("Data內會", "20260101", "https://doc.url", "Drive/path")
        assert msg.startswith("2026/01/01 的 Data內會")

    def test_contains_doc_url(self):
        msg = build_message("Data內會", "20260101", "https://example.com/doc", "Drive/path")
        assert "https://example.com/doc" in msg

    def test_contains_drive_path(self):
        msg = build_message("Data內會", "20260101", "https://doc.url", "週一週四_Data_內會/20260101")
        assert "週一週四_Data_內會/20260101" in msg

    def test_message_structure(self):
        msg = build_message("PM會議", "20260101", "https://doc.url", "Drive/PM")
        assert "📄 連結：" in msg
        assert "📂 雲端：" in msg

    def test_invalid_date_fallback(self):
        # 無效日期不應拋出例外，而是 fallback 顯示日期
        msg = build_message("Data內會", "99999999", "https://doc.url", "Drive/path")
        assert "Data內會" in msg


# ─── send_notification ────────────────────────────────────────────────────────

class TestSendNotification:
    def test_success(self):
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ok": True}

        with patch("send_slack_notification.load_token", return_value="xoxb-fake"), \
             patch("send_slack_notification.WebClient", return_value=mock_client):
            from send_slack_notification import send_notification
            result = send_notification("C123", "https://doc.url", "Drive/path", "Data內會", "20260101")

        assert result is True
        mock_client.chat_postMessage.assert_called_once_with(
            channel="C123",
            text=build_message("Data內會", "20260101", "https://doc.url", "Drive/path"),
        )

    def test_api_error_returns_false(self):
        from slack_sdk.errors import SlackApiError

        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = SlackApiError(
            "not_in_channel", {"error": "not_in_channel"}
        )

        with patch("send_slack_notification.load_token", return_value="xoxb-fake"), \
             patch("send_slack_notification.WebClient", return_value=mock_client):
            from send_slack_notification import send_notification
            result = send_notification("C123", "https://doc.url", "Drive/path", "Data內會", "20260101")

        assert result is False
