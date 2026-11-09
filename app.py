"""NIKKE screen translation: local OCR, text-only API, no game integration.

Two independent channels own their OCR region, provider, workers and chat.
Channel 1 automatically uses contextual tôi–cậu/cô/anh… while channel 2 is off,
and NIKKE em → anh while channel 2 is enabled; channel 2 uses Commander anh → em.
Tabs and chat visibility never select the voice. Each request freezes its
provider and role; role changes invalidate old results without erasing history.
The shell saves only safe per-channel settings under ``channels``; original
flat settings migrate into channel 1, while channel 2 starts without a region.
History and enabled state stay in memory and never enter settings. API keys
are kept in memory unless explicitly saved to the current user's Windows vault;
vault lookup is scoped to the exact normalized HTTPS API base endpoint.
Movable chats keep messages readable across OCR changes, empty scenes and pauses.
A lone underscore at the end of any OCR line is treated as a blinking cursor,
including story paragraphs followed by choices; internal underscores remain.
The translation provider is explicit: GPT API or OPUS CPU offline. GPT uses
contextual role instructions; OPUS adjusts reliably aligned singular pronouns
with less context awareness. OPUS never uses API credentials or falls back to
network translation on failure.
Screenshot mode temporarily includes chat windows in captures, pauses both
channels, and resumes only previously active channels that were not dismissed.
Frozen builds keep settings and model assets beside the executable; the
bundled _internal directory must remain alongside it.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QPoint, QRect, QRectF, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QSplitter, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from backend import APIConfig, TranslationConfig, TranslationError, Translator, WindowsOCR, load_key_file
from credentials import CredentialError, load_translation_key, normalize_endpoint, store_translation_key
from native import Hotkeys, TranslationChatPanel, set_capture_excluded
from offline import OpusTranslator

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
SETTINGS = ROOT / 'settings.json'
DEFAULT_ENDPOINT = 'https://api.openai.com/v1'
DEFAULT_MODEL = 'gpt-4.1-mini'


class OCRWorker(QObject):
    result = Signal(str, int)
    error = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.ocr = None

    @Slot(bytes, int)
    def recognize(self, png, generation):
        try:
            if self.ocr is None:
                self.ocr = WindowsOCR()
            self.result.emit(self.ocr.read(png), generation)
        except TranslationError as exc:
            self.error.emit(str(exc), generation)
        except Exception:
            self.error.emit('OCR gặp lỗi. Hãy thử chọn lại vùng chụp.', generation)


class TranslationWorker(QObject):
    result = Signal(str, str, int, bool, float)
    error = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.opus = None

    @Slot()
    def release_local(self):
        if self.opus is not None:
            self.opus.close()
            self.opus = None

    @Slot(str, object, int, bool)
    def translate(self, text, config, generation, probe):
        client = None
        started = time.monotonic()
        try:
            if config.provider == 'opus':
                if self.opus is None:
                    try:
                        self.opus = OpusTranslator()
                    except Exception:
                        raise TranslationError(
                            'Không nạp được OPUS offline. Kiểm tra models/opus và các thư viện đi kèm ứng dụng. Không tự chuyển sang API.'
                        ) from None
                translated = self.opus.translate(text, config.speaker_role)
            elif config.provider == 'api' and config.api is not None:
                self.release_local()
                client = Translator(config.api)
                translated = client.translate(text, config.speaker_role)
            else:
                raise TranslationError('Bộ dịch chưa được cấu hình hợp lệ.')
            self.result.emit(text, translated, generation, probe, time.monotonic() - started)
        except TranslationError as exc:
            self.error.emit(str(exc), generation)
        except Exception:
            self.error.emit('Bộ dịch gặp lỗi. Hãy kiểm tra cấu hình rồi bật lại; không tự chuyển bộ dịch.', generation)
        finally:
            if client is not None:
                client.close()


class RegionSelector(QDialog):
    def __init__(self, screen, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('Chọn vùng hội thoại — Escape để hủy')
        self.backdrop = screen.grabWindow(0)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.origin = None
        self.selection = QRect()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.backdrop)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 130))
        if not self.selection.isEmpty():
            painter.save()
            painter.setClipRect(self.selection)
            painter.drawPixmap(self.rect(), self.backdrop)
            painter.restore()
            painter.setPen(QPen(QColor('#79e7cc'), 2))
            painter.drawRect(self.selection)
        painter.setPen(QColor('white'))
        painter.setFont(QFont('Segoe UI', 15))
        painter.drawText(QRect(30, 25, self.width() - 60, 80), Qt.TextFlag.TextWordWrap,
                         'Kéo chuột khoanh vùng chữ tiếng Anh. Thả chuột để chọn · Esc để hủy')

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.selection = QRect(self.origin, self.origin)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.origin is not None:
            self.selection = QRect(self.origin, event.position().toPoint()).normalized().intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.origin is not None:
            self.selection = QRect(self.origin, event.position().toPoint()).normalized().intersected(self.rect())
            if self.selection.width() >= 40 and self.selection.height() >= 20:
                self.accept()
            else:
                self.origin = None
                self.selection = QRect()
                self.update()


class DialogueFixture(QWidget):
    SENTENCES = (
        'I trust you. Please stay with me.',
        'Rapi, stay with me. We will return home together.',
        'Anis, the Raptures are approaching. Prepare for battle!',
    )

    def __init__(self):
        super().__init__()
        self.setWindowTitle('NIKKE — Hội thoại mẫu')
        self.resize(820, 310)
        self.index = 0
        layout = QVBoxLayout(self)
        heading = QLabel('HỘI THOẠI MẪU • chữ thật để kiểm tra OCR')
        heading.setObjectName('eyebrow')
        layout.addWidget(heading)
        self.dialogue = QLabel(self.SENTENCES[0])
        self.dialogue.setWordWrap(True)
        self.dialogue.setTextFormat(Qt.TextFormat.PlainText)
        self.dialogue.setStyleSheet('font-size: 26px; color: #ffffff; padding: 24px; background: #152236; border-radius: 12px;')
        self.dialogue.setMinimumHeight(145)
        layout.addWidget(self.dialogue)
        next_button = QPushButton('Câu tiếp theo')
        next_button.clicked.connect(self.next_sentence)
        layout.addWidget(next_button)

    def next_sentence(self):
        self.index = (self.index + 1) % len(self.SENTENCES)
        self.dialogue.setText(self.SENTENCES[self.index])


class TranslationChannel(QWidget):
    request_ocr = Signal(bytes, int)
    request_translation = Signal(str, object, int, bool)

    def __init__(self, owner, index, saved, key_file=None):
        super().__init__(owner)
        self.owner = owner
        self.index = index
        self.speaker_role = 'neutral' if index == 0 else 'commander'
        self.enabled = False
        self.active_config = None
        self.generation = 0
        self.ocr_busy = False
        self.api_busy = False
        self.single_ocr = False
        self.candidate = ''
        self.candidate_since = 0.0
        self.last_translated = ''
        self.empty_since = None
        self.closing = False
        self.capture_warnings = set()
        self.fixture = None
        self.region = [0.06, 0.58, 0.88, 0.29] if index == 0 else None
        self.panel_geometry = None
        self._endpoint_scope = None
        self._key_endpoint = None
        self._build_ui()
        self._load_settings(saved)
        panel_options = {} if index == 0 else {
            'title': 'k4f_chan · Lịch sử dịch 2',
            'accessible_name': 'Lịch sử dịch NIKKE 2',
            'history_accessible_name': 'Các tin nhắn đã dịch · Kênh 2',
        }
        self.overlay = TranslationChatPanel(**panel_options)
        self.overlay.place_on(self.screen_target().geometry())
        self.overlay.restore_placement(self.panel_geometry)
        self.panel_save_timer = QTimer(self)
        self.panel_save_timer.setSingleShot(True)
        self.panel_save_timer.setInterval(350)
        self.panel_save_timer.timeout.connect(self._save_settings)
        self.overlay.geometry_changed.connect(self.panel_save_timer.start)
        self.overlay.dismissed.connect(self._panel_dismissed)
        self.ocr_thread = QThread(self)
        self.ocr_worker = OCRWorker()
        self.ocr_worker.moveToThread(self.ocr_thread)
        self.request_ocr.connect(self.ocr_worker.recognize)
        self.ocr_worker.result.connect(self._ocr_result)
        self.ocr_worker.error.connect(self._ocr_error)
        self.ocr_thread.finished.connect(self.ocr_worker.deleteLater)
        self.ocr_thread.start()
        self.api_thread = QThread(self)
        self.api_worker = TranslationWorker()
        self.api_worker.moveToThread(self.api_thread)
        self.request_translation.connect(self.api_worker.translate)
        self.api_worker.result.connect(self._translation_result)
        self.api_worker.error.connect(self._api_error)
        self.api_thread.finished.connect(self.api_worker.release_local, Qt.ConnectionType.DirectConnection)
        self.api_thread.finished.connect(self.api_worker.deleteLater)
        self.api_thread.start()
        self.timer = QTimer(self)
        self.timer.setInterval(450)
        self.timer.timeout.connect(self.capture)
        self.timer.start()
        self.endpoint.textChanged.connect(self._endpoint_changed)
        self.endpoint.editingFinished.connect(self._restore_saved_key)
        self.key.textChanged.connect(self._key_changed)
        self._restore_saved_key()
        if key_file:
            self._load_key(key_file)
        self.screen_box.currentIndexChanged.connect(self._capture_settings_changed)
        self.mode_box.currentIndexChanged.connect(self._capture_settings_changed)
        self.provider_box.currentIndexChanged.connect(self._provider_changed)
        self._update_provider_controls()
        self._update_region_label()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(9)
        eyebrow = QLabel('SCREEN SUBTITLES  /  LOCAL OCR')
        eyebrow.setObjectName('eyebrow')
        layout.addWidget(eyebrow)
        title = QLabel('k4f_chan  /  NIKKE' if self.index == 0 else 'Nhân vật chính  /  Tiếng Việt')
        title.setObjectName('title')
        layout.addWidget(title)
        subtitle = QLabel('OCR trên máy · Chọn OPUS offline hoặc GPT API · Không can thiệp game.')
        subtitle.setWordWrap(True)
        subtitle.setObjectName('muted')
        layout.addWidget(subtitle)
        self.status = QLabel('ĐÃ TẠM DỪNG · Chọn vùng hội thoại rồi bật dịch')
        self.status.setObjectName('status')
        self.status.setWordWrap(True)
        self.status.setAccessibleName('Trạng thái dịch')
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.toggle_button = QPushButton('Bật dịch  ·  Ctrl+Alt+T')
        self.toggle_button.setObjectName('primary')
        self.toggle_button.clicked.connect(self.toggle_translation)
        row.addWidget(self.toggle_button, 2)
        self.mode_box = QComboBox()
        self.mode_box.addItems(['Hội thoại', 'Toàn màn hình'])
        self.mode_box.setAccessibleName('Chế độ dịch')
        self.mode_box.setToolTip('Ctrl+Alt+F để chuyển chế độ. Toàn màn hình có thể đọc cả chữ riêng tư đang hiển thị.')
        row.addWidget(self.mode_box, 1)
        layout.addLayout(row)
        capture_form = QFormLayout()
        self.provider_box = QComboBox()
        self.provider_box.addItem('GPT API', 'api')
        self.provider_box.addItem('OPUS offline · CPU', 'opus')
        self.provider_box.setAccessibleName('Bộ dịch')
        capture_form.addRow('Bộ dịch', self.provider_box)
        self.voice_hint = QLabel()
        self.voice_hint.setWordWrap(True)
        self._update_voice_hint()
        capture_form.addRow('Xưng hô', self.voice_hint)
        self.provider_hint = QLabel()
        self.provider_hint.setWordWrap(True)
        self.provider_hint.setObjectName('muted')
        capture_form.addRow('', self.provider_hint)
        self.screen_box = QComboBox()
        for i, screen in enumerate(QApplication.screens()):
            geo = screen.geometry()
            self.screen_box.addItem(f'{i + 1} · {screen.name()} · {geo.width()} × {geo.height()}')
        self.screen_box.setAccessibleName('Màn hình chụp')
        capture_form.addRow('Màn hình', self.screen_box)
        region_row = QHBoxLayout()
        region_button = QPushButton('Khoanh vùng hội thoại')
        region_button.clicked.connect(self.choose_region)
        reset_button = QPushButton('Vùng mặc định' if self.index == 0 else 'Xóa vùng kênh 2')
        reset_button.clicked.connect(self.reset_region)
        region_row.addWidget(region_button)
        region_row.addWidget(reset_button)
        capture_form.addRow('Vùng chữ', region_row)
        self.region_label = QLabel()
        self.region_label.setObjectName('muted')
        capture_form.addRow('', self.region_label)
        chat_row = QHBoxLayout()
        chat_button = QPushButton('Mở khung chat')
        chat_button.clicked.connect(lambda: self.show_chat_panel())
        chat_reset = QPushButton('Đặt lại vị trí chat')
        chat_reset.clicked.connect(lambda: self.show_chat_panel(reset=True))
        chat_row.addWidget(chat_button)
        chat_row.addWidget(chat_reset)
        capture_form.addRow('Bản dịch', chat_row)
        layout.addLayout(capture_form)
        self.api_frame = QFrame()
        self.api_frame.setObjectName('card')
        api_layout = QFormLayout(self.api_frame)
        api_layout.setContentsMargins(15, 12, 15, 12)
        self.endpoint = QLineEdit(DEFAULT_ENDPOINT)
        self.endpoint.setAccessibleName('API base URL')
        self.model = QLineEdit(DEFAULT_MODEL)
        self.model.setAccessibleName('Model GPT')
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('Nhập hoặc nạp key · Bấm Lưu key vào Windows để dùng lại')
        self.key.setAccessibleName('Khóa API bảo mật')
        key_row = QHBoxLayout()
        key_row.addWidget(self.key, 1)
        load_button = QPushButton('Nạp key từ tệp')
        load_button.clicked.connect(self.choose_key_file)
        key_row.addWidget(load_button)
        self.save_key_button = QPushButton('Lưu key vào Windows')
        self.save_key_button.setAccessibleName('Lưu key vào Windows cho endpoint hiện tại')
        self.save_key_button.clicked.connect(self._save_key)
        key_row.addWidget(self.save_key_button)
        api_layout.addRow('API base URL', self.endpoint)
        api_layout.addRow('Model', self.model)
        api_layout.addRow('API key', key_row)
        self.key_status = QLabel('Chưa nạp key · Windows vault riêng theo endpoint và tài khoản Windows')
        self.key_status.setWordWrap(True)
        self.key_status.setObjectName('muted')
        api_layout.addRow('', self.key_status)
        layout.addWidget(self.api_frame)
        self.model.textEdited.connect(self._api_settings_edited)
        tools = QHBoxLayout()
        self.ocr_button = QPushButton('Thử OCR · không gửi API')
        self.ocr_button.clicked.connect(self.test_ocr)
        self.probe_button = QPushButton('Kiểm tra GPT')
        self.probe_button.clicked.connect(self.test_translation)
        fixture_button = QPushButton('Mở hội thoại mẫu')
        fixture_button.clicked.connect(self.show_fixture)
        tools.addWidget(self.ocr_button)
        tools.addWidget(self.probe_button)
        tools.addWidget(fixture_button)
        layout.addLayout(tools)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.source = self._text_panel(splitter, 'CHỮ OCR · ENGLISH', 'Văn bản nhận được từ màn hình')
        self.translation = self._text_panel(splitter, 'BẢN DỊCH · TIẾNG VIỆT', 'Bản dịch tiếng Việt')
        layout.addWidget(splitter, 1)
        self.notice = QLabel('Bản dịch nằm trong khung chat bên phải. Kéo thanh tiêu đề để di chuyển; kéo cạnh/góc để đổi cỡ.\nMỗi câu cách một dòng trống, giữ 50 câu gần nhất trong phiên. Ctrl+Alt+F: đổi vùng dịch.\nDùng game cửa sổ / không viền. Không bảo đảm tương thích mọi anti-cheat.')
        self.notice.setWordWrap(True)
        self.notice.setObjectName('muted')
        layout.addWidget(self.notice)

    @staticmethod
    def _text_panel(splitter, title, accessible):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        label.setObjectName('eyebrow')
        layout.addWidget(label)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setAcceptRichText(False)
        text.setAccessibleName(accessible)
        text.setMinimumHeight(100)
        layout.addWidget(text)
        splitter.addWidget(panel)
        return text

    def _load_settings(self, settings):
        region = settings.get('region')
        if (isinstance(region, list) and len(region) == 4
                and all(type(v) in (int, float) and 0 <= v <= 1 for v in region)
                and region[2] > 0 and region[3] > 0
                and region[0] + region[2] <= 1.001 and region[1] + region[3] <= 1.001):
            self.region = list(region)
        elif 'region' in settings and region is None:
            self.region = None
        self.endpoint.setText(str(settings.get('endpoint', DEFAULT_ENDPOINT)))
        self.model.setText(str(settings.get('model', DEFAULT_MODEL)))
        index = settings.get('screen', 0)
        if type(index) is int and 0 <= index < self.screen_box.count():
            self.screen_box.setCurrentIndex(index)
        self.panel_geometry = settings.get('chat_geometry')
        provider_index = self.provider_box.findData(settings.get('provider', 'api'))
        if provider_index >= 0:
            self.provider_box.setCurrentIndex(provider_index)

    def settings_data(self):
        # Credentials and URL query/userinfo never enter the portable settings.
        rect = self.overlay.geometry()
        try:
            endpoint = normalize_endpoint(self.endpoint.text().strip())
            valid = True
        except CredentialError:
            endpoint = DEFAULT_ENDPOINT
            valid = False
        return {
            'region': self.region,
            'screen': self.screen_box.currentIndex(),
            'chat_geometry': [rect.x(), rect.y(), rect.width(), rect.height()],
            'provider': self.provider_box.currentData(),
            'endpoint': endpoint,
            'model': self.model.text().strip() if valid else DEFAULT_MODEL,
        }

    def _save_settings(self):
        self.owner._save_settings()

    def _load_key(self, path):
        try:
            endpoint = normalize_endpoint(self.endpoint.text().strip())
            value = load_key_file(str(path))
            self._set_key(value, endpoint, 'Đã nạp tệp · Chưa lưu vào Windows; không sao chép tệp gốc')
            self._api_settings_edited()
        except (TranslationError, CredentialError) as exc:
            self.key_status.setText(str(exc))

    def choose_key_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Chọn tệp chứa API key', str(ROOT), 'Text files (*.txt *.env);;All files (*)')
        if path:
            self._load_key(path)

    def _set_key(self, value, endpoint, message):
        previous = self.key.blockSignals(True)
        try:
            self.key.setText(value)
        finally:
            self.key.blockSignals(previous)
        self._key_endpoint = endpoint if value else None
        self.key_status.setText(message)

    def _endpoint_changed(self):
        try:
            endpoint = normalize_endpoint(self.endpoint.text().strip())
        except CredentialError:
            endpoint = None
        if endpoint != self._endpoint_scope:
            self._endpoint_scope = endpoint
            self._set_key('', None, 'Endpoint đã đổi · Đã xóa key trong ô; chỉ nạp khóa khớp endpoint')
        self._api_settings_edited()

    def _restore_saved_key(self):
        try:
            endpoint = normalize_endpoint(self.endpoint.text().strip())
            self._endpoint_scope = endpoint
            if self.key.text() and self._key_endpoint == endpoint:
                return
            value = load_translation_key(endpoint)
            self._set_key(
                value or '', endpoint,
                'Đã nạp từ Windows · Chỉ endpoint này và tài khoản Windows hiện tại'
                if value else 'Endpoint này chưa có key đã lưu · Nhập hoặc nạp tệp rồi bấm Lưu key vào Windows',
            )
        except CredentialError as exc:
            self.key_status.setText(str(exc))

    def _key_changed(self):
        try:
            self._key_endpoint = normalize_endpoint(self.endpoint.text().strip()) if self.key.text() else None
        except CredentialError:
            self._key_endpoint = None
        self.key_status.setText(
            'Key đã sửa · Chỉ trong bộ nhớ đến khi bấm Lưu key vào Windows'
            if self.key.text() else 'Chưa nạp key · Không lưu key trong settings hoặc log'
        )
        self._api_settings_edited()

    def _save_key(self):
        try:
            endpoint = normalize_endpoint(self.endpoint.text().strip())
            if self._key_endpoint != endpoint or not self.key.text():
                raise CredentialError('Hãy nhập hoặc nạp key cho endpoint hiện tại trước khi lưu.')
            store_translation_key(endpoint, self.key.text().strip())
        except CredentialError as exc:
            self.key_status.setText(str(exc))
            return
        self.key_status.setText('Đã lưu vào Windows · Chỉ endpoint này và tài khoản Windows hiện tại; không nằm trong thư mục app')
        self._save_settings()

    def _update_voice_hint(self):
        if self.index == 0:
            text = ('Tự động · Kênh 2 bật: em → anh' if self.speaker_role == 'nikke'
                    else 'Tự động · Kênh 2 tắt: tôi → cậu/cô/anh… theo ngữ cảnh')
            explanation = (
                'Tự đổi theo trạng thái bật dịch của kênh 2, không theo tab hoặc khung chat đang mở. '
                'Kênh 2 tắt: xưng tôi, gọi người nghe theo ngữ cảnh; kênh 2 bật: NIKKE xưng em, gọi anh. '
                'Chọn vùng và chụp ảnh chỉ tạm dừng, giữ chế độ trước đó cho đến khi khôi phục.'
            )
        else:
            text = 'Commander: anh → em'
            explanation = 'Kênh 2 xưng anh, gọi em; bật dịch kênh này tự chuyển kênh 1 sang em → anh.'
        explanation += ' Giữ ngôi kể, tên riêng, số nhiều, lời trích dẫn và quan hệ thân tộc rõ trong câu.'
        self.voice_hint.setText(text)
        self.voice_hint.setAccessibleName('Xưng hô · ' + text)
        self.voice_hint.setToolTip(explanation)
        self.voice_hint.setAccessibleDescription(explanation)

    def _set_speaker_role(self, role):
        if self.speaker_role == role:
            return
        self.speaker_role = role
        self.generation += 1
        self.candidate = ''
        self.candidate_since = 0.0
        self.last_translated = ''
        self.empty_since = None
        if self.active_config is not None:
            # Replace only the voice of the frozen snapshot, not provider/key
            # values from widgets that may have changed since it was started.
            self.active_config = replace(self.active_config, speaker_role=role)
        self._update_voice_hint()

    def _api_settings_edited(self):
        if self.enabled or self.owner.screenshot_mode or self.owner.selecting_region:
            self._pause('Cấu hình API đã đổi. Bật dịch lại khi sẵn sàng.')
        else:
            self.generation += 1
        self.last_translated = ''

    def _provider_name(self):
        return 'OPUS offline' if self.provider_box.currentData() == 'opus' else 'GPT API'

    def _update_provider_controls(self):
        offline = self.provider_box.currentData() == 'opus'
        self.api_frame.setEnabled(not offline)
        self.probe_button.setText('Kiểm tra OPUS' if offline else 'Kiểm tra GPT')
        self.provider_hint.setText(
            'Chạy trên CPU, không cần mạng/key. Xưng hô dựa trên căn chỉnh từ Anh–Việt, hiểu ngữ cảnh kém hơn GPT; có thể sai thuật ngữ hoặc bỏ ý. Không tự gọi API.'
            if offline else 'Xưng hô theo vai kênh, xét ngữ cảnh và số nhiều. Chỉ gửi chữ OCR tới API đã cấu hình; không gửi ảnh.'
        )

    def _provider_changed(self):
        self._pause('Đã chọn ' + self._provider_name() + ' · Bật dịch khi sẵn sàng.')
        self.candidate = ''
        self.last_translated = ''
        self.empty_since = None
        self._update_provider_controls()
        self._save_settings()

    def screen_target(self):
        screens = QApplication.screens()
        index = self.screen_box.currentIndex()
        return screens[min(max(index, 0), len(screens) - 1)]

    def _update_region_label(self):
        if self.region is None:
            self.region_label.setText('Chưa chọn vùng hội thoại · Khoanh vùng riêng hoặc chọn Toàn màn hình')
            return
        x, y, w, h = self.region
        self.region_label.setText(f'Vùng hội thoại: x={x:.0%}, y={y:.0%}, rộng={w:.0%}, cao={h:.0%} · chỉ màn hình đã chọn')

    def _capture_settings_changed(self):
        self.generation += 1
        self.candidate = ''
        self.last_translated = ''
        self.empty_since = None
        self.translation.clear()
        previous_screen = self.overlay._screen
        self.overlay.place_on(self.screen_target().geometry())
        if self.index == 1 and previous_screen != self.screen_target().geometry():
            self.owner._place_secondary_panel()
        self._update_region_label()
        if self.enabled and self.region is None and self.mode_box.currentIndex() == 0:
            self._pause('Chưa chọn vùng hội thoại · Khoanh vùng riêng hoặc chọn Toàn màn hình')
        elif self.enabled:
            self.status.setText('ĐANG DỊCH · ' + self.mode_box.currentText() + ' · Chờ chữ ổn định')
        self._save_settings()

    def choose_region(self):
        self.owner.choose_region(self)

    def reset_region(self):
        self.region = [0.06, 0.58, 0.88, 0.29] if self.index == 0 else None
        self.mode_box.setCurrentIndex(0)
        self._capture_settings_changed()

    def toggle_mode(self):
        self.mode_box.setCurrentIndex(1 - self.mode_box.currentIndex())

    def _config(self):
        if self.provider_box.currentData() == 'opus':
            return TranslationConfig('opus', self.speaker_role)
        try:
            endpoint = normalize_endpoint(self.endpoint.text().strip())
        except CredentialError as exc:
            raise TranslationError(str(exc)) from None
        if not self.key.text().strip() or self._key_endpoint != endpoint:
            raise TranslationError('Hãy nhập hoặc nạp API key khớp endpoint hiện tại trước khi bật dịch.')
        config = APIConfig(endpoint, self.model.text().strip(), self.key.text().strip())
        # Construction validates without sending any request.
        client = Translator(config)
        client.close()
        return TranslationConfig('api', self.speaker_role, config)

    def toggle_translation(self):
        if self.closing or self.owner.selecting_region or self.owner.screenshot_mode:
            return
        if self.enabled:
            self._pause()
            return
        if self.mode_box.currentIndex() == 0 and self.region is None:
            self.status.setText('Chưa chọn vùng hội thoại · Khoanh vùng riêng hoặc chọn Toàn màn hình')
            return
        self.owner._sync_speaker_roles()
        try:
            self.active_config = self._config()
        except TranslationError as exc:
            self.status.setText(str(exc))
            return
        self.enabled = True
        self.generation += 1
        self.candidate = ''
        self.last_translated = ''
        self.empty_since = None
        self.toggle_button.setText('Tạm dừng  ·  Ctrl+Alt+T')
        self.show_chat_panel()
        self.status.setText('ĐANG DỊCH · ' + self._provider_name() + ' · ' + self.mode_box.currentText() + ' · Chờ chữ ổn định')
        self.owner._sync_speaker_roles()
        self._save_settings()

    def _pause(self, message='ĐÃ TẠM DỪNG · Không chụp màn hình, không gọi API mới', *, temporary=False):
        self.enabled = False
        self.generation += 1
        self.single_ocr = False
        self.toggle_button.setText('Bật dịch  ·  Ctrl+Alt+T')
        self.status.setText(message)
        if not temporary:
            if self.owner.screenshot_mode:
                self.owner.screenshot_resume[self.index] = (False, message)
            if self.owner.selecting_region:
                self.owner.selection_resume[self.index] = (False, message)
        self.owner._sync_speaker_roles()

    def show_chat_panel(self, *, reset=False):
        if self.closing:
            return
        self.overlay.place_on(self.screen_target().geometry(), reset=reset)
        if reset and self.index == 1:
            self.owner._place_secondary_panel()
        self.overlay.show()
        self._apply_capture_visibility()

    def _apply_capture_visibility(self):
        success = set_capture_excluded(self.overlay, not self.owner.screenshot_mode)
        if not success:
            self.notice.setText('Windows không đổi được chế độ chụp khung chat. Hãy mở lại khung chat hoặc chọn vùng OCR tránh app.')
        return success

    def _panel_dismissed(self):
        if not self.closing:
            self._pause('Đã đóng khung chat · Bật dịch hoặc bấm Mở khung chat để mở lại.')

    def test_ocr(self):
        if self.closing or self.owner.selecting_region or self.owner.screenshot_mode:
            return
        if self.mode_box.currentIndex() == 0 and self.region is None:
            self.status.setText('Chưa chọn vùng hội thoại · Khoanh vùng riêng hoặc chọn Toàn màn hình')
            return
        if not self.enabled:
            self.single_ocr = True
        self.capture()

    def test_translation(self):
        if self.closing or self.owner.selecting_region or self.owner.screenshot_mode:
            return
        if self.api_busy:
            self.status.setText('Đang có yêu cầu dịch; chờ hoàn tất trước khi kiểm tra.')
            return
        try:
            config = self._config()
        except TranslationError as exc:
            self.status.setText(str(exc))
            return
        self._pause('Đang kiểm tra ' + self._provider_name() + ' bằng một câu mẫu tiếng Anh…')
        self.api_busy = True
        self.probe_button.setEnabled(False)
        self.request_translation.emit(DialogueFixture.SENTENCES[0], config, self.generation, True)

    def show_fixture(self):
        if self.fixture is None:
            self.fixture = DialogueFixture()
        screen = self.screen_target().availableGeometry()
        self.fixture.move(screen.x() + 30, screen.y() + 100)
        self.fixture.show()
        self.notice.setText('Cửa sổ mẫu dùng chữ thật: khoanh vùng câu tiếng Anh rồi bật dịch để thử OCR → bộ dịch đã chọn → khung chat.')

    def capture(self):
        if self.closing or self.owner.selecting_region or self.owner.screenshot_mode or self.ocr_busy or not (self.enabled or self.single_ocr):
            return
        screen = self.screen_target()
        if self.mode_box.currentIndex() == 1:
            pixmap = screen.grabWindow(0)
        else:
            if self.region is None:
                self._pause('Chưa chọn vùng hội thoại · Khoanh vùng riêng hoặc chọn Toàn màn hình')
                return
            geo = screen.geometry()
            x, y, w, h = self.region
            pixmap = screen.grabWindow(0, round(geo.width() * x), round(geo.height() * y),
                                        max(1, round(geo.width() * w)), max(1, round(geo.height() * h)))
        if pixmap.isNull():
            self._pause('Không chụp được màn hình. Kiểm tra quyền chụp và dùng game cửa sổ / không viền.')
            return
        if max(pixmap.width(), pixmap.height()) > 3000:
            pixmap = pixmap.scaled(3000, 3000, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not pixmap.save(buffer, 'PNG'):
            self._pause('Không mã hóa được ảnh OCR.')
            return
        buffer.close()
        self.ocr_busy = True
        self.request_ocr.emit(bytes(data), self.generation)

    @Slot(str, int)
    def _ocr_result(self, text, generation):
        self.ocr_busy = False
        if self.closing or generation != self.generation:
            return
        self.source.setPlainText(text)
        if self.single_ocr and not self.enabled:
            self.single_ocr = False
            self.status.setText('OCR cục bộ hoàn tất · Không gửi chữ lên API' if text else 'OCR chưa thấy chữ. Hãy chọn lại vùng.')
            return
        if not self.enabled:
            return
        # Normalize before joining lines: story cards can have a blinking
        # paragraph cursor followed by choice/UI lines in the same OCR region.
        lines = []
        for line in text.splitlines():
            line = line.rstrip()
            if line.endswith('_') and not line.endswith('__'):
                line = line[:-1]
            lines.append(line)
        candidate = ' '.join(' '.join(lines).split())
        now = time.monotonic()
        if candidate != self.candidate:
            self.candidate = candidate
            self.candidate_since = now
        if not candidate:
            if self.empty_since is None:
                self.empty_since = now
            # A single missed OCR frame must not blink a readable subtitle.
            if now - self.empty_since >= 1.8:
                self.last_translated = ''
                self.translation.clear()
            return
        self.empty_since = None
        if (candidate != self.last_translated and now - self.candidate_since >= 0.75 and not self.api_busy):
            self.api_busy = True
            self.probe_button.setEnabled(False)
            self.status.setText('ĐANG DỊCH · ' + self._provider_name() + ' đang xử lý câu mới…')
            self.request_translation.emit(candidate, self.active_config, generation, False)

    @Slot(str, str, int, bool, float)
    def _translation_result(self, source, translated, generation, probe, elapsed):
        self.api_busy = False
        self.probe_button.setEnabled(True)
        if self.closing or generation != self.generation:
            return
        if probe:
            self.source.setPlainText(source)
            self.translation.setPlainText(translated)
            self.status.setText(f'{self._provider_name()} hoạt động · {elapsed:.1f}s · Đang tạm dừng')
            self.overlay.set_subtitle(translated)
            self.show_chat_panel()
            self._save_settings()
        elif self.enabled and source == self.candidate:
            self.last_translated = source
            self.translation.setPlainText(translated)
            self.overlay.set_subtitle(translated)
            self.show_chat_panel()
            self.status.setText(f'ĐANG DỊCH · {self._provider_name()} · {self.mode_box.currentText()} · Câu mới: {elapsed:.1f}s')

    @Slot(str, int)
    def _ocr_error(self, message, generation):
        self.ocr_busy = False
        if generation == self.generation and not self.closing:
            self._pause(message)

    @Slot(str, int)
    def _api_error(self, message, generation):
        self.api_busy = False
        self.probe_button.setEnabled(True)
        if generation == self.generation and not self.closing:
            self._pause(message)

    def _begin_shutdown(self):
        if self.closing:
            return
        self.closing = True
        self.timer.stop()
        self._pause('Đang đóng an toàn; chờ yêu cầu đang chạy hoàn tất…')
        self.panel_save_timer.stop()
        self.overlay.close()
        if self.fixture:
            self.fixture.close()
        self.ocr_thread.quit()
        self.api_thread.quit()
        self.setEnabled(False)

    def workers_running(self):
        # A zero-time wait also covers native thread cleanup after finished.
        return not self.ocr_thread.wait(0) or not self.api_thread.wait(0)

    def closeEvent(self, event):
        if not self.closing:
            self._save_settings()
            self._begin_shutdown()
        if self.workers_running():
            event.ignore()
            QTimer.singleShot(100, self, self.close)
            return
        self.key.clear()
        event.accept()


class ArtworkBackground(QWidget):
    """One local artwork behind the controls; no animation or network access."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('artworkBackground')
        self._artwork = QPixmap(str(ROOT / 'assets' / 'interface-background.jpg'))
        self._source_rect = QRectF(self._artwork.rect())
        self._base_color = QColor('#0c1421')
        self._shade = QColor(5, 10, 23, 112)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._artwork.isNull() or self.width() <= 0 or self.height() <= 0:
            return
        image_width, image_height = self._artwork.width(), self._artwork.height()
        aspect = self.width() / self.height()
        if aspect >= image_width / image_height:
            crop_width, crop_height = image_width, image_width / aspect
        else:
            crop_width, crop_height = image_height * aspect, image_height
        # Keep the face near the upper-middle even in a wide/maximized window.
        top = max(0.0, min(image_height - crop_height, 0.32 * (image_height - crop_height)))
        self._source_rect = QRectF((image_width - crop_width) / 2, top, crop_width, crop_height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._base_color)
        if not self._artwork.isNull():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(QRectF(self.rect()), self._artwork, self._source_rect)
            painter.fillRect(self.rect(), self._shade)


class MainWindow(QMainWindow):
    """Independent channel runtimes with one automatic voice dependency."""

    def __init__(self, key_file=None):
        super().__init__()
        self.setWindowTitle('k4f_chan · Anh → Việt')
        self.resize(790, 1000)
        self.setMinimumSize(660, 680)
        self.closing = False
        self.selecting_region = False
        self.screenshot_mode = False
        self.screenshot_resume = [(False, ''), (False, '')]
        self.selection_resume = [(False, ''), (False, '')]
        self.restoring_channels = False
        self.channels: list[TranslationChannel] = []
        self.tabs = QTabWidget(self)
        central = ArtworkBackground(self)
        shell_layout = QVBoxLayout(central)
        shell_layout.setContentsMargins(8, 8, 8, 0)
        self.screenshot_button = QPushButton('Chế độ chụp ảnh · Hiện khung chat trong ảnh')
        self.screenshot_button.setCheckable(True)
        self.screenshot_button.setAccessibleName('Chế độ chụp ảnh')
        self.screenshot_hint = QLabel('Bật trước khi chụp bằng Win+Shift+S; tắt sau khi chụp để tiếp tục dịch.')
        self.screenshot_hint.setWordWrap(True)
        shell_layout.addWidget(self.screenshot_button)
        shell_layout.addWidget(self.screenshot_hint)
        shell_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        saved = self._load_settings()
        first = TranslationChannel(self, 0, saved[0], key_file)
        self.channels.append(first)
        inherited = first.settings_data()
        second_settings = {
            key: inherited[key] for key in ('screen', 'provider', 'endpoint', 'model')
        }
        second_settings.update(saved[1])
        second = TranslationChannel(self, 1, second_settings)
        self.channels.append(second)
        if not self._valid_panel_geometry(second.panel_geometry):
            self._place_secondary_panel()
        for channel, label in zip(self.channels, ('Kênh 1 · NIKKE', 'Kênh 2 · Nhân vật chính')):
            scroll = QScrollArea(self.tabs)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.viewport().setAutoFillBackground(False)
            scroll.setWidget(channel)
            self.tabs.addTab(scroll, label)
        self.screenshot_button.toggled.connect(self._set_screenshot_mode)
        self.hotkeys = Hotkeys(self)
        self.hotkeys.toggle_requested.connect(self.toggle_translation)
        self.hotkeys.mode_requested.connect(self.toggle_mode)
        warnings = self.hotkeys.start()
        if warnings:
            for channel in self.channels:
                channel.notice.setText('\n'.join(warnings))
        QTimer.singleShot(0, self, self._exclude_controls)

    @staticmethod
    def _load_settings():
        try:
            settings = json.loads(SETTINGS.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return [{}, {}]
        if not isinstance(settings, dict):
            return [{}, {}]
        if 'channels' not in settings:
            return [settings, {}]
        channels = settings['channels']
        if not isinstance(channels, list):
            return [{}, {}]
        return [
            channels[i] if i < len(channels) and isinstance(channels[i], dict) else {}
            for i in range(2)
        ]

    @staticmethod
    def _valid_panel_geometry(value):
        return (isinstance(value, list) and len(value) == 4
                and all(type(item) is int for item in value)
                and value[2] >= 220 and value[3] >= 220)

    def _save_settings(self):
        if len(self.channels) != 2:
            return
        data = {'channels': [channel.settings_data() for channel in self.channels]}
        try:
            SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError:
            for channel in self.channels:
                channel.notice.setText('Không lưu được cấu hình. Không có key nào được ghi vào settings; Windows vault không thay đổi.')

    def _place_secondary_panel(self):
        first, second = self.channels
        screen = second.screen_target().geometry()
        panel = second.overlay
        panel.place_on(screen, reset=True)
        first_rect = first.overlay.geometry()
        width, height = panel.width(), panel.height()
        left = screen.x() + 16
        right = screen.x() + screen.width() - width - 16
        # Oppose the first panel's actual saved side, not a fixed right default.
        x = left if first_rect.center().x() >= screen.center().x() else right
        y = panel.y()
        if first.screen_target() == second.screen_target():
            available = (first_rect.left() - left - 12 if x == left
                         else screen.right() - first_rect.right() - 28)
            if available >= panel.minimumWidth():
                width = min(width, available)
                if x != left:
                    x = screen.x() + screen.width() - width - 16
        panel.setGeometry(x, y, width, height)

    def _sync_speaker_roles(self):
        if (self.closing or self.selecting_region or self.screenshot_mode
                or self.restoring_channels or len(self.channels) != 2):
            return
        first, second = self.channels
        if not first.closing:
            first._set_speaker_role('nikke' if second.enabled and not second.closing else 'neutral')

    def _restore_channels(self, previous, *, resume=True):
        self.restoring_channels = True
        try:
            for channel, (was_enabled, status) in zip(self.channels, previous):
                if self.closing:
                    break
                if channel.closing:
                    continue
                if resume and was_enabled:
                    channel.toggle_translation()
                elif resume:
                    channel.status.setText(status)
        finally:
            self.restoring_channels = False
            self._sync_speaker_roles()

    def _set_screenshot_mode(self, active):
        if self.closing or self.selecting_region or active == self.screenshot_mode:
            return
        if active:
            self.screenshot_resume = [(channel.enabled, channel.status.text()) for channel in self.channels]
            self.screenshot_mode = True
            for channel in self.channels:
                channel._pause('CHẾ ĐỘ CHỤP ẢNH · Tạm dừng OCR và dịch', temporary=True)
            self.tabs.setEnabled(False)
        else:
            self.screenshot_mode = False
            self.tabs.setEnabled(True)
        applied = [
            channel._apply_capture_visibility()
            for channel in self.channels if channel.overlay.isVisible()
        ]
        success = all(applied)
        if active:
            self.screenshot_hint.setText(
                'ĐANG CHỤP ẢNH · Hai kênh đã tạm dừng. Dùng Win+Shift+S rồi tắt nút này để tiếp tục dịch.'
                if success else 'Windows chưa cho hiện đủ khung chat trong ảnh. Dịch vẫn tạm dừng; thử mở lại app.'
            )
        else:
            self.screenshot_hint.setText(
                'Đã ẩn khung chat khỏi ảnh chụp; các kênh được khôi phục trạng thái trước khi chụp.'
                if success else 'Không khôi phục được bộ lọc chụp ảnh; giữ tạm dừng dịch để tránh OCR tự đọc.'
            )
            previous = self.screenshot_resume
            self.screenshot_resume = [(False, ''), (False, '')]
            self._restore_channels(previous, resume=success)

    def toggle_translation(self):
        if not self.closing and not self.selecting_region and not self.screenshot_mode:
            self.channels[self.tabs.currentIndex()].toggle_translation()

    def toggle_mode(self):
        if not self.closing and not self.selecting_region and not self.screenshot_mode:
            self.channels[self.tabs.currentIndex()].toggle_mode()

    def choose_region(self, channel):
        if self.closing or self.selecting_region or self.screenshot_mode:
            return
        self.selection_resume = [(item.enabled, item.status.text()) for item in self.channels]
        self.selecting_region = True
        for item in self.channels:
            item._pause('Đang chọn vùng hội thoại · Tạm dừng cả hai kênh', temporary=True)
        selector = RegionSelector(channel.screen_target(), self)
        try:
            if selector.exec() == QDialog.DialogCode.Accepted and not self.closing:
                rect = selector.selection
                channel.region = [
                    rect.x() / selector.width(), rect.y() / selector.height(),
                    rect.width() / selector.width(), rect.height() / selector.height(),
                ]
                channel.mode_box.setCurrentIndex(0)
                channel._capture_settings_changed()
        finally:
            selector.deleteLater()
            self.selecting_region = False
            previous = self.selection_resume
            self.selection_resume = [(False, ''), (False, '')]
            if not self.closing:
                self._restore_channels(previous)

    def _exclude_controls(self):
        if self.closing:
            return
        if not set_capture_excluded(self, True):
            for channel in self.channels:
                channel.notice.setText('Windows không loại trừ được cửa sổ app khỏi ảnh chụp. Hãy thu nhỏ app, tránh chụp vào app/phụ đề; dùng chế độ cửa sổ hoặc không viền.')
        self.channels[0].show_chat_panel()

    def closeEvent(self, event):
        if not self.closing:
            self.closing = True
            self._save_settings()
            self.hotkeys.close()
            for channel in self.channels:
                channel._begin_shutdown()
            self.setEnabled(False)
        if any(channel.workers_running() for channel in self.channels):
            event.ignore()
            QTimer.singleShot(100, self, self.close)
            return
        for channel in self.channels:
            channel.key.clear()
        event.accept()


STYLE = '''
QWidget { background: transparent; color: #edf2fa; font-family: "Segoe UI"; font-size: 13px; }
QMainWindow, QDialog, DialogueFixture { background: #0c1421; }
QTabWidget::pane { background: transparent; border: none; }
QTabBar::tab { background: rgba(10, 18, 32, 224); border: 1px solid #34445f; padding: 10px 16px; margin-right: 3px; }
QTabBar::tab:selected { background: rgba(22, 42, 58, 238); color: #a5f4df; border-bottom: 2px solid #79e7cc; }
QLabel#title { font-size: 30px; font-weight: 700; letter-spacing: -1px; }
QLabel#eyebrow { color: #79e7cc; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
QLabel#muted { color: #c0cede; font-size: 11px; }
QLabel#status { color: #b4f8e3; background: rgba(15, 40, 43, 232); border: 1px solid #3b6669; border-radius: 10px; padding: 12px; }
QFrame#card { background: rgba(12, 21, 37, 221); border: 1px solid #3a4a63; border-radius: 12px; }
QLineEdit, QComboBox, QTextEdit { background: rgba(12, 22, 38, 226); border: 1px solid #435570; border-radius: 7px; padding: 8px; selection-background-color: #286f67; }
QLineEdit, QComboBox { min-height: 20px; }
QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border: 1px solid #79e7cc; }
QPushButton { background: rgba(19, 33, 52, 232); border: 1px solid #4a607d; border-radius: 8px; padding: 10px 12px; min-height: 16px; font-weight: 600; }
QPushButton:hover { background: #29415d; border-color: #79e7cc; }
QPushButton:disabled { color: #9aa9bc; background: rgba(20, 31, 47, 220); }
QPushButton#primary { background: #79e7cc; color: #0c2726; border: none; font-weight: 700; }
QPushButton#primary:hover { background: #a1f2df; }
QComboBox QAbstractItemView { background: #142437; color: #e8eef6; selection-background-color: #286f67; }
QSplitter::handle { background: #263a51; }
'''


def main():
    parser = argparse.ArgumentParser(description='Local Windows OCR → GPT → Vietnamese screen subtitles')
    parser.add_argument('--key-file', type=Path, help='Read API key into channel 1 memory only; file is not modified')
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName('k4f_chan')
    app.setWindowIcon(QIcon(str(ROOT / 'assets' / 'app.ico')))
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window = MainWindow(args.key_file)
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
