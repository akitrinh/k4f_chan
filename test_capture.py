"""Screenshot-mode state transitions; no capture, model or API IO."""
from unittest.mock import patch
from PySide6.QtTest import QSignalSpy
from test_subtitles import DualChannelTestCase


class ScreenshotModeTests(DualChannelTestCase):
    def setUp(self):
        super().setUp()
        self.affinity = patch('app.set_capture_excluded', return_value=True)
        self.affinity.start()
        self.addCleanup(self.affinity.stop)

    def test_pauses_capture_and_stale_results_then_resumes_only_active_channel(self):
        requests = self.enable_offline(self.channel)
        ocr = QSignalSpy(self.channel.request_ocr)
        self.channel.overlay.set_subtitle('Em tin anh.')
        self.other.overlay.set_subtitle('Anh tin em.')
        old_generation = self.channel.generation
        mode = self.channel.mode_box.currentIndex()
        self.window.screenshot_button.click()
        self.assertTrue(self.window.screenshot_mode)
        self.assertFalse(self.channel.enabled)
        self.assertFalse(self.other.enabled)
        self.assertFalse(self.window.tabs.isEnabled())
        self.channel.test_ocr()
        self.channel.capture()
        self.channel.test_translation()
        self.window.toggle_translation()
        self.window.toggle_mode()
        self.assertEqual(ocr.count(), 0)
        self.assertEqual(requests.count(), 0)
        self.assertEqual(self.channel.mode_box.currentIndex(), mode)
        self.channel._translation_result('Old request', 'Không được ghi đè ảnh.', old_generation, True, 0.1)
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), 'Em tin anh.')
        self.window.screenshot_button.click()
        self.assertFalse(self.window.screenshot_mode)
        self.assertTrue(self.window.tabs.isEnabled())
        self.assertTrue(self.channel.enabled)
        self.assertFalse(self.other.enabled)
        self.assertEqual(self.other.overlay.history_view.toPlainText(), 'Anh tin em.')

    def test_closing_chat_while_photographing_cancels_its_resume(self):
        self.enable_offline(self.channel)
        self.enable_offline(self.other, region=[.1,.2,.5,.2])
        self.other.overlay.set_subtitle('Lịch sử vẫn giữ.')
        self.window.screenshot_button.click()
        self.other.overlay.close()
        self.window.screenshot_button.click()
        self.assertTrue(self.channel.enabled)
        self.assertFalse(self.other.enabled)
        self.assertFalse(self.other.overlay.isVisible())
        self.assertEqual(self.other.overlay.history_view.toPlainText(), 'Lịch sử vẫn giữ.')

    def test_failed_restore_keeps_translation_paused(self):
        self.enable_offline(self.channel)
        self.window.screenshot_button.click()
        with patch('app.set_capture_excluded', return_value=False):
            self.window.screenshot_button.click()
        self.assertFalse(self.channel.enabled)
        self.assertFalse(self.other.enabled)
        self.assertTrue(self.window.tabs.isEnabled())

    def test_photo_mode_is_session_only(self):
        self.window.screenshot_button.click()
        self.window._save_settings()
        restored = self.open_window()
        self.assertFalse(restored.screenshot_mode)
        self.assertFalse(restored.screenshot_button.isChecked())
        self.assertTrue(all(not channel.enabled for channel in restored.channels))
