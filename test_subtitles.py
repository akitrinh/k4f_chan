"""Subtitle/channel regressions; no API calls or access to the user's Windows vault."""
import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication, QEvent, QRect
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QDialog
from app import MainWindow, TranslationWorker
from backend import APIConfig, TranslationConfig
from native import TranslationChatPanel


class DualChannelTestCase(unittest.TestCase):
    """Real channel state and worker lifetimes, without capture or translation IO."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(['test_subtitles', '-platform', 'offscreen'])

    def initial_settings(self):
        return None

    def setUp(self):
        self.files = TemporaryDirectory(prefix='test_', dir=Path(__file__).parent)
        self.settings = Path(self.files.name) / 'settings.json'
        self.settings_patch = patch('app.SETTINGS', self.settings)
        self.settings_patch.start()
        self.hotkeys_patch = patch('app.Hotkeys.start', return_value=[])
        self.hotkeys_patch.start()
        self.vault_patch = patch('app.load_translation_key', return_value=None)
        self.vault_patch.start()
        self.addCleanup(self.vault_patch.stop)
        self.windows = []
        saved = self.initial_settings()
        if saved is not None:
            self.settings.write_text(json.dumps(saved), encoding='utf-8')
        self.window = self.open_window()
        self.channel = self.window.channels[0]
        self.other = self.window.channels[1]

    def open_window(self):
        window = MainWindow()
        self.windows.append(window)
        window.hotkeys.close()
        for channel in window.channels:
            channel.timer.stop()
            channel.panel_save_timer.stop()
        # Drain context-bound initial placement/exclusion callbacks before a
        # test starts, with capture timers stopped and both channels paused.
        self.app.processEvents()
        for channel in window.channels:
            channel.panel_save_timer.stop()
        return window

    def tearDown(self):
        try:
            for window in reversed(self.windows):
                window.hotkeys.close()
                for channel in window.channels:
                    channel.timer.stop()
                    channel.panel_save_timer.stop()
                window.close()
                for channel in window.channels:
                    channel.ocr_thread.quit()
                    channel.api_thread.quit()
                    self.assertTrue(channel.ocr_thread.wait(3000), 'OCR thread did not stop')
                    self.assertTrue(channel.api_thread.wait(3000), 'Translation thread did not stop')
                window.close()
                for channel in window.channels:
                    channel.overlay.deleteLater()
                window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        finally:
            self.hotkeys_patch.stop()
            self.settings_patch.stop()
            self.files.cleanup()

    def enable_offline(self, channel, *, region=None):
        # Selecting OPUS validates without constructing a model. Disconnect
        # only the work boundary: channel state, signals and result slots run.
        channel.request_translation.disconnect(channel.api_worker.translate)
        channel.request_ocr.disconnect(channel.ocr_worker.recognize)
        channel.provider_box.setCurrentIndex(channel.provider_box.findData('opus'))
        if region is not None:
            channel.region = list(region)
        channel.toggle_translation()
        self.assertTrue(channel.enabled)
        return QSignalSpy(channel.request_translation)

    def stable_ocr(self, channel, text, start):
        with patch('app.time.monotonic', side_effect=[start, start + 0.45, start + 0.9]):
            for _ in range(3):
                channel._ocr_result(text, channel.generation)

    def assert_voice(self, role):
        self.assertEqual(self.channel.speaker_role, role)
        self.assertEqual(self.other.speaker_role, 'commander')
        hint = self.channel.voice_hint
        self.assertIn('em → anh' if role == 'nikke' else 'tôi →', hint.text())
        self.assertIn(hint.text(), hint.accessibleName())
        self.assertEqual(hint.accessibleDescription(), hint.toolTip())
        self.assertIn('kênh 2', hint.toolTip())


class SubtitleContinuityTests(DualChannelTestCase):
    def setUp(self):
        super().setUp()
        self.channel.enabled = True
        self.channel.api_busy = True  # No network; model a real request still in flight.
        self.channel.candidate = 'An old complete line.'
        self.channel.last_translated = self.channel.candidate
        self.channel.translation.setPlainText('Bản dịch đang đọc.')
        self.channel.overlay.place_on(QRect(0, 0, 1920, 1080))
        self.channel.overlay.set_subtitle('Bản dịch đang đọc.')
        self.channel.overlay.show()
        self.generation = self.channel.generation

    def test_typewriter_and_single_missed_frame_keep_readable_subtitle(self):
        for text in ('Com', 'Commander,', '', 'Commander, stay with me.'):
            self.channel._ocr_result(text, self.generation)
            self.assertTrue(self.channel.overlay.isVisible())
            self.assertEqual(self.channel.translation.toPlainText(), 'Bản dịch đang đọc.')
        self.channel._translation_result('Commander, stay with me.', 'Chỉ huy, hãy ở bên tôi.', self.generation, False, 0.8)
        self.assertTrue(self.channel.overlay.isVisible())
        self.assertEqual(self.channel.translation.toPlainText(), 'Chỉ huy, hãy ở bên tôi.')

    def test_blinking_end_cursor_does_not_reset_stability_or_repeat_translation(self):
        self.channel.request_translation.disconnect(self.channel.api_worker.translate)
        requests = QSignalSpy(self.channel.request_translation)
        self.channel.api_busy = False
        self.channel.active_config = TranslationConfig('api', 'nikke', APIConfig('https://api.openai.com/v1', 'gpt-4.1-mini', 'unused-test-key'))
        sentence = 'Rapi_unit_01, stay with me.'
        with patch('app.time.monotonic', side_effect=[100.0, 100.45, 100.9, 101.35, 101.8]):
            for text in (sentence + '_', sentence, sentence + ' _'):
                self.channel._ocr_result(text, self.generation)
            self.assertEqual(requests.count(), 1)
            self.assertEqual(requests.at(0)[0], sentence)
            self.channel._translation_result(sentence, 'Rapi_unit_01, hãy ở bên tôi.', self.generation, False, 0.2)
            self.channel._ocr_result(sentence, self.generation)
            self.channel._ocr_result(sentence + '_', self.generation)
        self.assertEqual(requests.count(), 1)
        self.assertEqual(self.channel.translation.toPlainText(), 'Rapi_unit_01, hãy ở bên tôi.')

    def test_story_cursor_before_choices_does_not_block_translation(self):
        self.channel.request_translation.disconnect(self.channel.api_worker.translate)
        requests = QSignalSpy(self.channel.request_translation)
        self.channel.api_busy = False
        self.channel.active_config = TranslationConfig('opus', 'nikke')
        cursor_on = "Maria's Record\nwelcome Maria. _\nWalk forward.\nFind somewhere to hide.\nID: Rapi_unit_01\nLiteral __"
        cursor_off = cursor_on.replace('Maria. _', 'Maria.')
        with patch('app.time.monotonic', side_effect=[200.0, 200.45, 200.9]):
            for text in (cursor_on, cursor_off, cursor_on):
                self.channel._ocr_result(text, self.generation)
        self.assertEqual(requests.count(), 1)
        self.assertEqual(
            requests.at(0)[0],
            "Maria's Record welcome Maria. Walk forward. Find somewhere to hide. ID: Rapi_unit_01 Literal __",
        )

    def test_selecting_offline_needs_no_key_and_invalidates_pending_api_result(self):
        with patch('app.Translator', side_effect=AssertionError('Offline must not construct an API client')):
            self.channel.key.clear()
            self.channel.provider_box.setCurrentIndex(self.channel.provider_box.findData('opus'))
            config = self.channel._config()
            self.assertEqual(config.provider, 'opus')
            self.assertEqual(config.speaker_role, 'neutral')
            self.assertIsNone(config.api)
            self.assertFalse(self.channel.enabled)
            self.channel._translation_result(
                'An old complete line.', 'A stale API result must not be shown.',
                self.generation, False, 0.5,
            )
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), 'Bản dịch đang đọc.')

    def test_offline_load_failure_reports_error_without_calling_api(self):
        worker = TranslationWorker()
        worker.setParent(self.window)
        failures = QSignalSpy(worker.error)
        successes = QSignalSpy(worker.result)
        with patch('app.OpusTranslator', side_effect=RuntimeError('missing model')), patch('app.Translator') as api:
            worker.translate('Commander, help us.', TranslationConfig('opus', 'nikke'), 1, False)
            api.assert_not_called()
        self.assertEqual(failures.count(), 1)
        self.assertEqual(successes.count(), 0)

    def test_history_survives_empty_scenes_and_pauses(self):
        self.channel._ocr_result('', self.generation)
        self.channel.empty_since = time.monotonic() - 2.0
        self.channel._ocr_result('', self.generation)
        self.channel._pause()
        self.assertTrue(self.channel.overlay.isVisible())
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), 'Bản dịch đang đọc.')

    def test_old_request_cannot_overwrite_new_dialogue_or_resume_after_pause(self):
        self.channel.candidate = 'A different current line.'
        self.channel._translation_result('An old complete line.', 'Không được xuất hiện.', self.generation, False, 0.8)
        self.assertEqual(self.channel.translation.toPlainText(), 'Bản dịch đang đọc.')
        self.channel._pause()
        self.channel._translation_result('A different current line.', 'Không được xuất hiện.', self.generation, False, 0.8)
        self.assertTrue(self.channel.overlay.isVisible())
        self.assertEqual(self.channel.translation.toPlainText(), 'Bản dịch đang đọc.')
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), 'Bản dịch đang đọc.')


class ChannelIndependenceTests(DualChannelTestCase):
    def test_each_toggle_keeps_its_own_results_and_history(self):
        first_requests = self.enable_offline(self.channel)
        second_requests = self.enable_offline(self.other, region=[0.1, 0.15, 0.7, 0.2])
        sentence = 'Commander, which path should we take?'
        self.stable_ocr(self.channel, sentence, 300.0)
        self.stable_ocr(self.other, sentence, 400.0)
        first_generation = self.channel.generation
        second_generation = self.other.generation
        self.assertEqual(first_requests.count(), 1)
        self.assertEqual(second_requests.count(), 1)
        self.assertEqual(first_requests.at(0)[1].speaker_role, 'nikke')
        self.assertEqual(second_requests.at(0)[1].speaker_role, 'commander')
        self.channel._translation_result(sentence, 'Rapi: Chúng ta đi bên trái.', first_generation, False, 0.2)
        self.other._translation_result(sentence, 'Tôi: Chọn đường bên phải.', second_generation, False, 0.3)
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), 'Rapi: Chúng ta đi bên trái.')
        self.assertEqual(self.other.overlay.history_view.toPlainText(), 'Tôi: Chọn đường bên phải.')
        self.assertEqual(self.channel.translation.toPlainText(), 'Rapi: Chúng ta đi bên trái.')
        self.assertEqual(self.other.translation.toPlainText(), 'Tôi: Chọn đường bên phải.')

        self.other.toggle_button.click()
        self.assertFalse(self.other.enabled)
        self.assertTrue(self.channel.enabled)
        self.assertGreater(self.channel.generation, first_generation)
        self.assertEqual(self.channel.speaker_role, 'neutral')
        self.assertEqual(self.other.overlay.history_view.toPlainText(), 'Tôi: Chọn đường bên phải.')
        self.other.toggle_button.click()
        self.assertTrue(self.other.enabled)
        self.other._translation_result(sentence, 'Kết quả cũ không được thêm.', second_generation, False, 0.1)
        self.assertEqual(self.other.overlay.history_view.toPlainText(), 'Tôi: Chọn đường bên phải.')
        self.stable_ocr(self.other, 'Let us move forward.', 500.0)
        self.other._translation_result(
            'Let us move forward.', 'Tôi: Tiến về phía trước.', self.other.generation, False, 0.2,
        )
        self.assertEqual(second_requests.count(), 2)
        self.assertEqual(
            self.other.overlay.history_view.toPlainText(),
            'Tôi: Chọn đường bên phải.\n\nTôi: Tiến về phía trước.',
        )
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), 'Rapi: Chúng ta đi bên trái.')
        self.assertEqual(first_requests.count(), 1)

    def test_pausing_second_rejects_first_inflight_result_and_retranslates_same_text(self):
        first_requests = self.enable_offline(self.channel)
        self.enable_offline(self.other, region=[0.1, 0.15, 0.7, 0.2])
        source = 'Rapi, cover us.'
        self.channel.overlay.set_subtitle('Lịch sử vẫn đọc được.')
        self.stable_ocr(self.channel, source, 600.0)
        self.stable_ocr(self.other, 'I will protect everyone.', 700.0)
        _, paired_config, first_generation, _ = first_requests.at(0)
        second_generation = self.other.generation
        self.other._pause()
        self.assertTrue(self.channel.enabled)
        self.assertTrue(self.channel.api_busy)
        self.assertGreater(self.channel.generation, first_generation)
        self.assertEqual(paired_config.speaker_role, 'nikke')
        self.assertEqual(self.channel.active_config.speaker_role, 'neutral')
        # No new request is queued behind the cancelled in-flight work.
        self.stable_ocr(self.channel, source, 710.0)
        self.assertEqual(first_requests.count(), 1)
        self.other._translation_result(
            'I will protect everyone.', 'Kết quả đã hủy.', second_generation, False, 0.4,
        )
        self.channel._translation_result(source, 'Em sẽ bảo vệ anh.', first_generation, False, 0.4)
        self.assertEqual(self.other.overlay.history_view.toPlainText(), '')
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), 'Lịch sử vẫn đọc được.')
        self.assertFalse(self.channel.api_busy)
        self.stable_ocr(self.channel, source, 720.0)
        self.assertEqual(first_requests.count(), 2)
        self.assertEqual(first_requests.at(1)[0], source)
        self.assertEqual(first_requests.at(1)[1].speaker_role, 'neutral')
        self.channel._translation_result(
            source, 'Rapi, hãy yểm trợ chúng tôi.', first_requests.at(1)[2], False, 0.4,
        )
        self.assertEqual(self.channel.translation.toPlainText(), 'Rapi, hãy yểm trợ chúng tôi.')
        self.assertEqual(
            self.channel.overlay.history_view.toPlainText(),
            'Lịch sử vẫn đọc được.\n\nRapi, hãy yểm trợ chúng tôi.',
        )

    def test_reconfiguring_first_does_not_invalidate_second_inflight_result(self):
        self.enable_offline(self.channel)
        self.enable_offline(self.other, region=[0.1, 0.15, 0.7, 0.2])
        self.stable_ocr(self.channel, 'Wait here.', 800.0)
        self.stable_ocr(self.other, 'I choose to stay.', 900.0)
        first_generation, second_generation = self.channel.generation, self.other.generation
        self.channel.provider_box.setCurrentIndex(self.channel.provider_box.findData('api'))
        self.channel.endpoint.setText('https://translator.example/v1')
        self.channel.endpoint.textEdited.emit(self.channel.endpoint.text())
        self.channel.mode_box.setCurrentIndex(1)
        self.assertFalse(self.channel.enabled)
        self.assertTrue(self.other.enabled)
        self.assertTrue(self.other.api_busy)
        self.assertEqual(self.other.generation, second_generation)
        self.assertEqual(self.other.active_config.provider, 'opus')
        self.assertEqual(self.other.active_config.speaker_role, 'commander')
        self.channel._translation_result('Wait here.', 'Kết quả cấu hình cũ.', first_generation, False, 0.5)
        self.other._translation_result('I choose to stay.', 'Tôi chọn ở lại.', second_generation, False, 0.5)
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), '')
        self.assertEqual(self.other.translation.toPlainText(), 'Tôi chọn ở lại.')
        self.assertEqual(self.other.overlay.history_view.toPlainText(), 'Tôi chọn ở lại.')

    def test_closing_second_chat_changes_first_voice_without_erasing_either_history(self):
        first_requests = self.enable_offline(self.channel)
        self.enable_offline(self.other, region=[0.1, 0.15, 0.7, 0.2])
        self.other.overlay.set_subtitle('Lịch sử nhân vật chính.')
        self.stable_ocr(self.channel, 'The Ark is safe.', 1000.0)
        generation = self.channel.generation
        self.other.overlay.close()
        self.app.processEvents()
        self.assertFalse(self.other.enabled)
        self.assertFalse(self.other.overlay.isVisible())
        self.assertEqual(self.other.overlay.history_view.toPlainText(), 'Lịch sử nhân vật chính.')
        self.assertTrue(self.channel.enabled)
        self.assertTrue(self.channel.overlay.isVisible())
        self.assertGreater(self.channel.generation, generation)
        self.assertEqual(self.channel.speaker_role, 'neutral')
        self.channel._translation_result('The Ark is safe.', 'Kết quả vai cũ.', generation, False, 0.2)
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), '')
        self.stable_ocr(self.channel, 'The Ark is safe.', 1010.0)
        self.assertEqual(first_requests.count(), 2)
        self.channel._translation_result(
            'The Ark is safe.', 'Ark đã an toàn.', first_requests.at(1)[2], False, 0.2,
        )
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), 'Ark đã an toàn.')
        self.assertEqual(self.other.overlay.history_view.toPlainText(), 'Lịch sử nhân vật chính.')
        self.other.show_chat_panel()
        self.assertTrue(self.other.overlay.isVisible())
        self.assertFalse(self.other.enabled)
        self.assertEqual(self.channel.speaker_role, 'neutral')

    def test_switching_tabs_keeps_background_channel_processing(self):
        first_requests = self.enable_offline(self.channel)
        second_requests = self.enable_offline(self.other, region=[0.1, 0.15, 0.7, 0.2])
        generations = [channel.generation for channel in self.window.channels]
        self.window.tabs.setCurrentIndex(1)
        self.stable_ocr(self.channel, 'Rapi is speaking in the background.', 1100.0)
        self.window.tabs.setCurrentIndex(0)
        self.stable_ocr(self.other, 'My answer is still being read.', 1200.0)
        self.assertEqual(first_requests.count(), 1)
        self.assertEqual(second_requests.count(), 1)
        self.assertEqual(first_requests.at(0)[1].speaker_role, 'nikke')
        self.assertEqual(second_requests.at(0)[1].speaker_role, 'commander')
        self.assertTrue(all(channel.enabled for channel in self.window.channels))
        self.assertEqual([channel.generation for channel in self.window.channels], generations)
        self.channel._translation_result(
            'Rapi is speaking in the background.', 'Rapi vẫn đang nói.', generations[0], False, 0.2,
        )
        self.other._translation_result(
            'My answer is still being read.', 'Câu trả lời của tôi vẫn được đọc.', generations[1], False, 0.2,
        )
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), 'Rapi vẫn đang nói.')
        self.assertEqual(self.other.overlay.history_view.toPlainText(), 'Câu trả lời của tôi vẫn được đọc.')

    def test_mixed_provider_requests_keep_channel_roles_across_tabs_and_reconfiguration(self):
        roles = ('neutral', 'commander')
        source = 'I trust you. Please stay with me.'
        requests = []
        original = []
        for index, channel in enumerate(self.window.channels):
            channel.request_translation.disconnect(channel.api_worker.translate)
            channel.request_ocr.disconnect(channel.ocr_worker.recognize)
            requests.append(QSignalSpy(channel.request_translation))
            channel.key.setText('unused-role-snapshot-test-key')
            channel.region = [0.1, 0.15, 0.7, 0.2]
            provider = 'api' if index == 0 else 'opus'
            channel.provider_box.setCurrentIndex(channel.provider_box.findData(provider))
            channel.toggle_translation()
            self.window.tabs.setCurrentIndex(1 - index)
            self.stable_ocr(channel, source, 1400.0 + index * 10)
            self.assertEqual(requests[index].count(), 1)
            text, config, generation, probe = requests[index].at(0)
            self.assertEqual(text, source)
            self.assertEqual(config.provider, provider)
            self.assertEqual(config.speaker_role, roles[index])
            self.assertFalse(probe)
            original.append((config, generation))
        for index, channel in enumerate(self.window.channels):
            provider = 'opus' if index == 0 else 'api'
            channel.provider_box.setCurrentIndex(channel.provider_box.findData(provider))
            # Complete the old request after changing provider. Its frozen
            # configuration stays intact, but its stale result cannot appear.
            previous, generation = original[index]
            channel._translation_result(source, 'Kết quả cũ không được hiển thị.', generation, False, 0.2)
            self.assertEqual(channel.overlay.history_view.toPlainText(), '')
            self.assertEqual(previous.provider, 'api' if index == 0 else 'opus')
            self.assertEqual(previous.speaker_role, roles[index])
            self.window.tabs.setCurrentIndex(1 - index)
            channel.test_translation()
            self.assertEqual(requests[index].count(), 2)
            text, config, _, probe = requests[index].at(1)
            self.assertEqual(text, source)
            self.assertEqual(config.provider, provider)
            self.assertEqual(config.speaker_role, ('nikke', 'commander')[index])
            self.assertEqual(config.api is None, provider == 'opus')
            self.assertTrue(probe)

    def test_unconfigured_second_cannot_start_dialogue_capture_or_translation(self):
        self.assertIsNone(self.other.region)
        self.assertFalse(self.other.enabled)
        self.assertFalse(self.other.overlay.isVisible())
        self.other.provider_box.setCurrentIndex(self.other.provider_box.findData('opus'))
        self.other.request_ocr.disconnect(self.other.ocr_worker.recognize)
        self.other.request_translation.disconnect(self.other.api_worker.translate)
        captures = QSignalSpy(self.other.request_ocr)
        translations = QSignalSpy(self.other.request_translation)
        self.other.toggle_button.click()
        self.other.test_ocr()
        self.other.capture()
        self.stable_ocr(self.other, 'This must not be sent.', 1300.0)
        self.assertFalse(self.other.enabled)
        self.assertFalse(self.other.single_ocr)
        self.assertFalse(self.other.ocr_busy)
        self.assertFalse(self.other.api_busy)
        self.assertEqual(captures.count(), 0)
        self.assertEqual(translations.count(), 0)
        self.assertEqual(self.other.overlay.history_view.toPlainText(), '')
        # Full-screen is an explicit alternative to defining an ROI.
        self.other.mode_box.setCurrentIndex(1)
        self.other.toggle_button.click()
        self.assertTrue(self.other.enabled)
        self.assertTrue(self.other.overlay.isVisible())
        self.assertIsNone(self.other.region)

    def test_unconfigured_second_can_explicitly_probe_without_starting_capture(self):
        self.other.provider_box.setCurrentIndex(self.other.provider_box.findData('opus'))
        self.other.request_translation.disconnect(self.other.api_worker.translate)
        self.other.request_ocr.disconnect(self.other.ocr_worker.recognize)
        requests = QSignalSpy(self.other.request_translation)
        captures = QSignalSpy(self.other.request_ocr)
        first_generation = self.channel.generation
        self.other.test_translation()
        self.assertEqual(requests.count(), 1)
        source, config, generation, probe = requests.at(0)
        self.assertEqual(source, 'I trust you. Please stay with me.')
        self.assertEqual(config.provider, 'opus')
        self.assertEqual(config.speaker_role, 'commander')
        self.assertTrue(probe)
        self.assertFalse(self.other.enabled)
        self.assertIsNone(self.other.region)
        self.assertEqual(captures.count(), 0)
        self.other._translation_result(source, 'Anh tin em. Xin hãy ở bên anh.', generation, probe, 0.2)
        self.assertEqual(self.other.translation.toPlainText(), 'Anh tin em. Xin hãy ở bên anh.')
        self.assertEqual(self.other.overlay.history_view.toPlainText(), 'Anh tin em. Xin hãy ở bên anh.')
        self.assertTrue(self.other.overlay.isVisible())
        self.assertFalse(self.other.enabled)
        self.assertEqual(self.channel.generation, first_generation)
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), '')

    def test_reset_second_region_does_not_reset_first_or_capture_without_roi(self):
        self.enable_offline(self.channel)
        self.enable_offline(self.other, region=[0.1, 0.15, 0.7, 0.2])
        self.other.overlay.set_subtitle('Giữ lại lịch sử sau khi đặt lại vùng.')
        first_region = list(self.channel.region)
        first_generation = self.channel.generation
        captures = QSignalSpy(self.other.request_ocr)
        translations = QSignalSpy(self.other.request_translation)
        self.other.reset_region()
        self.other.capture()
        self.other.toggle_button.click()
        self.assertIsNone(self.other.region)
        self.assertFalse(self.other.enabled)
        self.assertEqual(captures.count(), 0)
        self.assertEqual(translations.count(), 0)
        self.assertEqual(self.channel.region, first_region)
        self.assertTrue(self.channel.enabled)
        self.assertGreater(self.channel.generation, first_generation)
        self.assertEqual(self.channel.speaker_role, 'neutral')
        self.assertEqual(self.other.overlay.history_view.toPlainText(), 'Giữ lại lịch sử sau khi đặt lại vùng.')


class AutomaticVoiceTests(DualChannelTestCase):
    def test_initial_neutral_voice_ignores_tabs_and_inactive_chat_visibility(self):
        requests = self.enable_offline(self.channel)
        self.assert_voice('neutral')
        generation = self.channel.generation
        source = 'I will stay here with you.'
        self.stable_ocr(self.channel, source, 1500.0)
        self.other.show_chat_panel()
        self.window.tabs.setCurrentIndex(1)
        self.other.overlay.hide()
        self.other.show_chat_panel()
        self.other.overlay.close()
        self.window.tabs.setCurrentIndex(0)
        self.assertFalse(self.other.enabled)
        self.assertEqual(self.channel.generation, generation)
        self.assert_voice('neutral')
        self.channel._translation_result(source, 'Tôi sẽ ở đây cùng cậu.', generation, False, 0.2)
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), 'Tôi sẽ ở đây cùng cậu.')
        self.stable_ocr(self.channel, source, 1510.0)
        self.assertEqual(requests.count(), 1)

    def test_successful_enable_freezes_api_request_and_retranslates_unchanged_text_each_way(self):
        self.channel.request_translation.disconnect(self.channel.api_worker.translate)
        self.channel.request_ocr.disconnect(self.channel.ocr_worker.recognize)
        self.channel.key.setText('unit-private-role-key')
        self.channel.toggle_translation()
        self.assertTrue(self.channel.enabled)
        requests = QSignalSpy(self.channel.request_translation)
        source = 'I trust you.'
        self.stable_ocr(self.channel, source, 1600.0)
        _, original, generation, _ = requests.at(0)
        self.assertEqual(original.speaker_role, 'neutral')
        self.enable_offline(self.other, region=[0.1, 0.15, 0.7, 0.2])
        self.assert_voice('nikke')
        self.assertIsNot(self.channel.active_config, original)
        self.assertIs(self.channel.active_config.api, original.api)
        self.assertEqual(original.speaker_role, 'neutral')
        self.channel._translation_result(source, 'Kết quả trung tính đã cũ.', generation, False, 0.2)
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), '')
        self.stable_ocr(self.channel, source, 1610.0)
        self.assertEqual(requests.count(), 2)
        paired = requests.at(1)[1]
        self.assertEqual(paired.speaker_role, 'nikke')
        self.channel._translation_result(source, 'Em tin anh.', requests.at(1)[2], False, 0.2)
        self.assertEqual(self.channel.last_translated, source)
        self.other.toggle_translation()
        self.assert_voice('neutral')
        self.assertEqual(self.channel.last_translated, '')
        self.assertEqual(paired.speaker_role, 'nikke')
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), 'Em tin anh.')
        self.stable_ocr(self.channel, source, 1620.0)
        self.assertEqual(requests.count(), 3)
        self.assertEqual(requests.at(2)[1].speaker_role, 'neutral')
        self.channel._translation_result(source, 'Tôi tin cậu.', requests.at(2)[2], False, 0.2)
        self.other.toggle_translation()
        self.assert_voice('nikke')
        self.stable_ocr(self.channel, source, 1630.0)
        self.assertEqual(requests.count(), 4)
        self.assertEqual(requests.at(3)[1].speaker_role, 'nikke')
        self.channel._translation_result(source, 'Em vẫn tin anh.', requests.at(3)[2], False, 0.2)
        self.assertEqual(
            self.channel.overlay.history_view.toPlainText(), 'Em tin anh.\n\nTôi tin cậu.\n\nEm vẫn tin anh.',
        )
        self.assertNotIn('unit-private-role-key', repr(self.channel.active_config))
        self.assertNotIn('unit-private-role-key', self.settings.read_text(encoding='utf-8'))
        self.assertNotIn('unit-private-role-key', self.channel.voice_hint.toolTip())

    def test_failed_second_enable_preserves_first_inflight_neutral_translation(self):
        requests = self.enable_offline(self.channel)
        source = 'I will wait for you.'
        self.stable_ocr(self.channel, source, 1700.0)
        generation = self.channel.generation
        config = self.channel.active_config
        self.other.toggle_translation()  # No region.
        self.assertFalse(self.other.enabled)
        self.other.region = [0.1, 0.15, 0.7, 0.2]
        self.other.toggle_translation()  # API has no key.
        self.assertFalse(self.other.enabled)
        self.assert_voice('neutral')
        self.assertEqual(self.channel.generation, generation)
        self.assertIs(self.channel.active_config, config)
        self.channel._translation_result(source, 'Tôi sẽ chờ cô.', generation, False, 0.2)
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), 'Tôi sẽ chờ cô.')
        self.stable_ocr(self.channel, source, 1710.0)
        self.assertEqual(requests.count(), 1)

    def test_second_errors_and_configuration_edits_cancel_paired_results(self):
        requests = self.enable_offline(self.channel)
        self.enable_offline(self.other, region=[0.1, 0.15, 0.7, 0.2])
        for index, action in enumerate(('provider', 'key', 'endpoint', 'model', 'ocr_error', 'api_error')):
            with self.subTest(action=action):
                source = f'I will protect you, unit {index}.'
                self.stable_ocr(self.channel, source, 1800.0 + index * 10)
                generation = self.channel.generation
                if action == 'provider':
                    self.other.provider_box.setCurrentIndex(self.other.provider_box.findData('api'))
                elif action == 'key':
                    self.other.key.setText('unit-config-change-key')
                elif action == 'endpoint':
                    self.other.endpoint.setText('https://changed.example/v1')
                elif action == 'model':
                    self.other.model.setText('changed-model')
                    self.other.model.textEdited.emit(self.other.model.text())
                elif action == 'ocr_error':
                    self.other._ocr_error('OCR không hoạt động.', self.other.generation)
                else:
                    self.other._api_error('Bộ dịch không hoạt động.', self.other.generation)
                self.assertFalse(self.other.enabled)
                self.assertTrue(self.channel.enabled)
                self.assert_voice('neutral')
                self.channel._translation_result(source, 'Kết quả em–anh đã cũ.', generation, False, 0.2)
                self.assertEqual(self.channel.overlay.history_view.toPlainText(), '')
                self.other.provider_box.setCurrentIndex(self.other.provider_box.findData('opus'))
                self.other.toggle_translation()
                self.assertTrue(self.other.enabled)
                self.assert_voice('nikke')
        self.assertEqual(requests.count(), 6)


class TemporaryVoiceSuspensionTests(DualChannelTestCase):
    def setUp(self):
        super().setUp()
        self.affinity_patch = patch('app.set_capture_excluded', return_value=True)
        self.affinity_patch.start()
        self.addCleanup(self.affinity_patch.stop)

    def test_screenshot_pause_keeps_paired_hint_and_only_restores_previously_active_channels(self):
        self.enable_offline(self.other, region=[0.1, 0.15, 0.7, 0.2])
        self.assert_voice('nikke')
        self.channel.status.setText('Kênh 1 đang nghỉ.')
        hint = self.channel.voice_hint.text()
        self.window.screenshot_button.click()
        self.assertFalse(self.channel.enabled)
        self.assertFalse(self.other.enabled)
        self.assert_voice('nikke')
        self.assertEqual(self.channel.voice_hint.text(), hint)
        self.window.screenshot_button.click()
        self.assertFalse(self.channel.enabled)
        self.assertTrue(self.other.enabled)
        self.assertEqual(self.channel.status.text(), 'Kênh 1 đang nghỉ.')
        self.assertEqual(self.channel.voice_hint.text(), hint)
        requests = self.enable_offline(self.channel)
        self.stable_ocr(self.channel, 'I can hear you.', 1900.0)
        self.assertEqual(requests.at(0)[1].speaker_role, 'nikke')
        self.channel._translation_result(
            'I can hear you.', 'Em nghe thấy anh.', requests.at(0)[2], False, 0.2,
        )
        self.assertEqual(self.channel.overlay.history_view.toPlainText(), 'Em nghe thấy anh.')

    def test_second_chat_dismissal_during_screenshot_restores_neutral_same_text_translation(self):
        requests = self.enable_offline(self.channel)
        self.enable_offline(self.other, region=[0.1, 0.15, 0.7, 0.2])
        source = 'I can see you.'
        self.stable_ocr(self.channel, source, 2000.0)
        old_generation = requests.at(0)[2]
        self.channel.overlay.set_subtitle('Lịch sử trước khi chụp.')
        self.other.overlay.set_subtitle('Lịch sử kênh 2.')
        self.window.screenshot_button.click()
        hint = self.channel.voice_hint.text()
        self.other.overlay.close()
        self.assert_voice('nikke')
        self.assertEqual(self.channel.voice_hint.text(), hint)
        self.channel._translation_result(source, 'Không được thêm em–anh.', old_generation, False, 0.2)
        self.window.screenshot_button.click()
        self.assertTrue(self.channel.enabled)
        self.assertFalse(self.other.enabled)
        self.assertFalse(self.other.overlay.isVisible())
        self.assert_voice('neutral')
        self.assertEqual(self.other.overlay.history_view.toPlainText(), 'Lịch sử kênh 2.')
        self.stable_ocr(self.channel, source, 2010.0)
        self.assertEqual(requests.count(), 2)
        self.assertEqual(requests.at(1)[1].speaker_role, 'neutral')
        self.channel._translation_result(source, 'Tôi nhìn thấy cậu.', requests.at(1)[2], False, 0.2)
        self.assertEqual(
            self.channel.overlay.history_view.toPlainText(),
            'Lịch sử trước khi chụp.\n\nTôi nhìn thấy cậu.',
        )
        self.other.show_chat_panel()
        self.assert_voice('neutral')

    def test_failed_screenshot_restore_reconciles_voice_with_both_channels_paused(self):
        self.enable_offline(self.channel)
        self.enable_offline(self.other, region=[0.1, 0.15, 0.7, 0.2])
        self.window.screenshot_button.click()
        self.assert_voice('nikke')
        with patch('app.set_capture_excluded', return_value=False):
            self.window.screenshot_button.click()
        self.assertFalse(self.channel.enabled)
        self.assertFalse(self.other.enabled)
        self.assert_voice('neutral')
        self.assertEqual(self.channel.active_config.speaker_role, 'neutral')

    def test_selection_accept_and_cancel_keep_voice_and_resume_both_channels(self):
        requests = self.enable_offline(self.channel)
        self.enable_offline(self.other, region=[0.1, 0.15, 0.7, 0.2])
        for index, result in enumerate((QDialog.DialogCode.Rejected, QDialog.DialogCode.Accepted)):
            with self.subTest(result=result), patch('app.RegionSelector') as selector_type:
                selector = selector_type.return_value
                selector.selection = QRect(10, 20, 300, 80)
                selector.width.return_value = 1000
                selector.height.return_value = 500
                hint = self.channel.voice_hint.text()

                def select():
                    self.assertTrue(self.window.selecting_region)
                    self.assertFalse(self.channel.enabled)
                    self.assertFalse(self.other.enabled)
                    self.assert_voice('nikke')
                    self.assertEqual(self.channel.voice_hint.text(), hint)
                    self.channel.toggle_translation()
                    self.channel.test_translation()
                    return result

                selector.exec.side_effect = select
                self.window.choose_region(self.other)
                self.assertFalse(self.window.selecting_region)
                self.assertTrue(self.channel.enabled)
                self.assertTrue(self.other.enabled)
                self.assert_voice('nikke')
                self.assertEqual(self.channel.voice_hint.text(), hint)
                self.stable_ocr(self.channel, 'I am still here.', 2100.0 + index * 10)
                self.channel._translation_result(
                    'I am still here.', f'Em vẫn ở đây, lượt {index}.', requests.at(index)[2], False, 0.2,
                )
        self.assertEqual(self.other.region, [0.01, 0.04, 0.3, 0.16])
        self.assertEqual(requests.count(), 2)
        self.assertEqual(
            self.channel.overlay.history_view.toPlainText(), 'Em vẫn ở đây, lượt 0.\n\nEm vẫn ở đây, lượt 1.',
        )

    def test_selection_dismissal_cancels_second_resume_and_updates_voice_after_dialog(self):
        requests = self.enable_offline(self.channel)
        self.enable_offline(self.other, region=[0.1, 0.15, 0.7, 0.2])
        self.channel.overlay.set_subtitle('Giữ lịch sử khi chọn vùng.')
        with patch('app.RegionSelector') as selector_type:
            def dismiss():
                self.other.overlay.close()
                self.assert_voice('nikke')
                return QDialog.DialogCode.Rejected

            selector_type.return_value.exec.side_effect = dismiss
            self.window.choose_region(self.channel)
        self.assertTrue(self.channel.enabled)
        self.assertFalse(self.other.enabled)
        self.assert_voice('neutral')
        self.stable_ocr(self.channel, 'I will return.', 2200.0)
        self.channel._translation_result(
            'I will return.', 'Tôi sẽ trở về.', requests.at(0)[2], False, 0.2,
        )
        self.assertEqual(
            self.channel.overlay.history_view.toPlainText(), 'Giữ lịch sử khi chọn vùng.\n\nTôi sẽ trở về.',
        )

    def test_shutdown_while_suspended_never_resumes_channels_or_loses_last_voice_hint(self):
        self.enable_offline(self.channel)
        self.enable_offline(self.other, region=[0.1, 0.15, 0.7, 0.2])
        hint = self.channel.voice_hint.text()
        self.window.screenshot_button.click()
        self.window.close()
        self.assertTrue(self.window.closing)
        self.window._set_screenshot_mode(False)
        self.assertTrue(all(channel.closing and not channel.enabled for channel in self.window.channels))
        self.assertEqual(self.channel.voice_hint.text(), hint)
        self.assertEqual(self.channel.speaker_role, 'nikke')


class ChannelSettingsTests(DualChannelTestCase):
    def initial_settings(self):
        screen = self.app.primaryScreen().geometry()
        width, height = min(300, (screen.width() - 64) // 2), min(380, screen.height() - 100)
        self.saved_geometry = [screen.right() - width - 24, screen.top() + 48, width, height]
        return {
            'region': [0.12, 0.62, 0.72, 0.23],
            'screen': 0,
            'chat_geometry': self.saved_geometry,
            'provider': 'opus',
            'endpoint': 'https://legacy.example/v1',
            'model': 'legacy-model',
            'key': 'legacy-secret-must-not-load',
            'history': ['Legacy private dialogue must not load.'],
            'enabled': True,
        }

    def test_flat_settings_keep_first_profile_and_place_unconfigured_second_opposite(self):
        self.assertEqual(len(self.window.channels), 2)
        self.assertEqual(self.channel.region, [0.12, 0.62, 0.72, 0.23])
        self.assertEqual(self.channel.overlay.geometry(), QRect(*self.saved_geometry))
        for channel in self.window.channels:
            self.assertEqual(channel.screen_box.currentIndex(), 0)
            self.assertEqual(channel.provider_box.currentData(), 'opus')
            self.assertEqual(channel.endpoint.text(), 'https://legacy.example/v1')
            self.assertEqual(channel.model.text(), 'legacy-model')
            self.assertEqual(channel.key.text(), '')
            self.assertFalse(channel.enabled)
            self.assertEqual(channel.overlay.history_view.toPlainText(), '')
        self.assertIsNone(self.other.region)
        self.assertFalse(self.other.overlay.isVisible())
        self.assertFalse(self.channel.overlay.geometry().intersects(self.other.overlay.geometry()))
        self.assertTrue(self.other.screen_target().geometry().contains(self.other.overlay.geometry()))
        self.assertNotEqual(
            self.channel.overlay.history_view.accessibleName(),
            self.other.overlay.history_view.accessibleName(),
        )

    def test_flat_saved_left_panel_puts_second_on_right_without_overlap(self):
        saved = self.initial_settings()
        screen = self.app.primaryScreen().geometry()
        saved['chat_geometry'] = [screen.left() + 24, screen.top() + 48, self.saved_geometry[2], self.saved_geometry[3]]
        self.settings.write_text(json.dumps(saved), encoding='utf-8')
        restored = self.open_window()
        first, second = restored.channels
        self.assertEqual(first.overlay.geometry(), QRect(*saved['chat_geometry']))
        self.assertGreater(second.overlay.geometry().left(), first.overlay.geometry().right())
        self.assertFalse(first.overlay.geometry().intersects(second.overlay.geometry()))
        self.assertTrue(screen.contains(second.overlay.geometry()))
        self.assertEqual(second.screen_box.currentIndex(), first.screen_box.currentIndex())
        self.assertIsNone(second.region)

    def test_two_profiles_round_trip_without_keys_history_or_enabled_state(self):
        regions = [[0.1, 0.5, 0.8, 0.25], [0.2, 0.1, 0.6, 0.3]]
        screen = self.app.primaryScreen().geometry()
        width, height = min(300, (screen.width() - 64) // 2), min(360, screen.height() - 100)
        geometries = [
            [screen.left() + 24, screen.top() + 48, width, height],
            [screen.right() - width - 24, screen.bottom() - height - 24, width, height],
        ]
        for index, channel in enumerate(self.window.channels):
            channel.region = list(regions[index])
            channel.provider_box.setCurrentIndex(channel.provider_box.findData('opus' if index == 0 else 'api'))
            channel.endpoint.setText(f'https://channel{index + 1}.example/v1')
            channel.model.setText(f'channel-{index + 1}-model')
            channel.key.setText(f'private-key-channel-{index + 1}')
            channel.source.setPlainText(f'Private source channel {index + 1}')
            channel.translation.setPlainText(f'Private translation channel {index + 1}')
            channel.overlay.set_subtitle(f'Private history channel {index + 1}')
            channel.overlay.setGeometry(QRect(*geometries[index]))
            channel.enabled = True
        self.window._save_settings()
        serialized = self.settings.read_text(encoding='utf-8')
        saved = json.loads(serialized)
        self.assertEqual(set(saved), {'channels'})
        self.assertEqual(len(saved['channels']), 2)
        for index, profile in enumerate(saved['channels']):
            self.assertEqual(
                set(profile), {'region', 'screen', 'chat_geometry', 'provider', 'endpoint', 'model'},
            )
            self.assertEqual(profile['region'], regions[index])
            self.assertEqual(profile['chat_geometry'], geometries[index])
            self.assertEqual(profile['screen'], 0)
            self.assertEqual(profile['provider'], 'opus' if index == 0 else 'api')
            self.assertEqual(profile['endpoint'], f'https://channel{index + 1}.example/v1')
            self.assertEqual(profile['model'], f'channel-{index + 1}-model')
        for private_value in (
            'private-key-channel-', 'Private source', 'Private translation',
            'Private history', 'legacy-secret', 'Legacy private', '"enabled"',
        ):
            self.assertNotIn(private_value, serialized)
        restored = self.open_window()
        for index, channel in enumerate(restored.channels):
            self.assertEqual(channel.region, regions[index])
            self.assertEqual(channel.overlay.geometry(), QRect(*geometries[index]))
            self.assertEqual(channel.provider_box.currentData(), 'opus' if index == 0 else 'api')
            self.assertEqual(channel.endpoint.text(), f'https://channel{index + 1}.example/v1')
            self.assertEqual(channel.model.text(), f'channel-{index + 1}-model')
            self.assertEqual(channel.key.text(), '')
            self.assertEqual(channel.source.toPlainText(), '')
            self.assertEqual(channel.translation.toPlainText(), '')
            self.assertEqual(channel.overlay.history_view.toPlainText(), '')
            self.assertFalse(channel.enabled)


class ChatPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(['test_chat', '-platform', 'offscreen'])

    def setUp(self):
        self.panel = TranslationChatPanel()
        self.screen = QRect(0, 0, 1920, 1080)
        self.panel.place_on(self.screen)

    def tearDown(self):
        self.panel.close()
        self.panel.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_starts_in_black_sidebar_and_preserves_dragged_layout_on_new_dialogue(self):
        self.assertGreaterEqual(self.panel.geometry().left(), 1440)
        self.assertTrue(self.screen.contains(self.panel.geometry()))
        self.panel.move(90, 130)
        self.panel.resize(300, 400)
        moved = self.panel.geometry()
        self.panel.set_subtitle('Chỉ huy, chúng ta phải bảo vệ Ark.')
        self.panel.place_on(self.screen)
        self.panel.set_subtitle('Rapi, mọi người đã sẵn sàng.')
        self.assertEqual(self.panel.geometry(), moved)
        self.assertEqual(
            self.panel.history_view.toPlainText(),
            'Chỉ huy, chúng ta phải bảo vệ Ark.\n\nRapi, mọi người đã sẵn sàng.',
        )

    def test_new_message_does_not_pull_reader_away_from_older_history(self):
        self.panel.resize(280, 240)
        self.panel.show()
        for index in range(25):
            self.panel.set_subtitle(f'Lượt {index}: Chỉ huy, chúng ta sẽ trở về nhà cùng nhau.')
        self.app.processEvents()
        scroll = self.panel.history_view.verticalScrollBar()
        scroll.setValue(0)
        self.panel.set_subtitle('Rapi: Câu mới nhất vẫn được thêm ở cuối lịch sử.')
        self.assertEqual(scroll.value(), 0)
        self.assertTrue(self.panel.history_view.toPlainText().startswith('Lượt 0:'))
        self.assertTrue(self.panel.history_view.toPlainText().endswith('Rapi: Câu mới nhất vẫn được thêm ở cuối lịch sử.'))

    def test_saved_layout_is_recovered_and_missing_monitor_is_clamped(self):
        self.panel.restore_placement([1500, 200, 300, 420])
        self.assertEqual(self.panel.geometry(), QRect(1500, 200, 300, 420))
        self.panel.restore_placement([-9000, 7000, 5000, 5000])
        self.assertTrue(self.screen.contains(self.panel.geometry()))


if __name__ == '__main__':
    unittest.main()
