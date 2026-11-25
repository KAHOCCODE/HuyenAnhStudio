"""Listen to voices without modifying or saving the open project."""
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
                              QPushButton, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QVBoxLayout)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from .core import preview_voice
from .voices import VOICES, PITCH_PRESETS, is_local_voice
from .voice_filters_ui import VoiceFilters

DEFAULT_SAMPLE = 'Xin chào, đây là giọng đọc bạn đang nghe thử. Chúc bạn có một ngày thật vui vẻ!'


class VoicePreviewDialog(QDialog):
    def __init__(self, owner, voice=None, text=None):
        super().__init__(owner)
        self.owner = owner
        self.running = False
        self.close_after_job = False
        self.setWindowTitle('Nghe thử giọng đọc')
        self.resize(640, 510)
        layout = QVBoxLayout(self)
        note = QLabel('Chọn giọng, nhập một câu bất kỳ rồi bấm Nghe thử. Không cần video hoặc SRT. Các lựa chọn ở đây chỉ dùng để nghe thử.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.voice = QComboBox()
        for label, value in VOICES.items():
            self.voice.addItem(label, value)
        self.voice.setCurrentIndex(max(0, self.voice.findData(voice or owner.p.voice)))
        self.voice.setMaxVisibleItems(12)
        self.filters = VoiceFilters(self.voice)
        form.addRow('Lọc giọng Việt', self.filters)
        form.addRow('Giọng đọc', self.voice)
        self.tone = QComboBox()
        for label, value in PITCH_PRESETS:
            self.tone.addItem(label, value)
        self.tone.addItem('Tùy chỉnh', None)
        form.addRow('Kiểu tông giọng', self.tone)
        self.pitch = QDoubleSpinBox()
        self.pitch.setRange(-6, 6)
        self.pitch.setDecimals(1)
        self.pitch.setSingleStep(.5)
        self.pitch.setValue(owner.p.tts_pitch)
        self.rate = QSpinBox()
        self.rate.setRange(-40, 100)
        self.rate.setSuffix(' %')
        self.rate.setValue(owner.p.tts_rate)
        form.addRow('Tông (bán âm)', self.pitch)
        form.addRow('Tốc độ đọc', self.rate)
        layout.addLayout(form)
        self.text = QPlainTextEdit(text or DEFAULT_SAMPLE)
        self.text.setPlaceholderText('Nhập một câu hoặc đoạn ngắn, tối đa 500 ký tự…')
        self.text.setMaximumHeight(130)
        layout.addWidget(self.text)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(1)
        self.player.setAudioOutput(self.audio)
        self.player.errorOccurred.connect(lambda *_: self.status.setText('Không phát được âm thanh: ' + self.player.errorString()))
        actions = QHBoxLayout()
        self.play = QPushButton('▶ Nghe thử')
        self.play.setObjectName('primary')
        self.play.clicked.connect(self.listen)
        actions.addWidget(self.play)
        self.stop = QPushButton('Dừng nghe')
        self.stop.clicked.connect(self.stop_or_cancel)
        actions.addWidget(self.stop)
        self.release = QPushButton('Giải phóng RAM')
        self.release.clicked.connect(self.release_model)
        actions.addWidget(self.release)
        layout.addLayout(actions)
        actions = QHBoxLayout()
        self.apply = QPushButton('Dùng lựa chọn này cho dự án')
        self.apply.clicked.connect(self.apply_to_project)
        actions.addWidget(self.apply)
        close = QPushButton('Đóng')
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        layout.addLayout(actions)
        self.voice.currentIndexChanged.connect(self.model_hint)
        self.tone.currentIndexChanged.connect(self.set_tone)
        self.pitch.valueChanged.connect(self.sync_tone)
        self.sync_tone()
        self.model_hint()

    def sync_tone(self, *_):
        self.tone.blockSignals(True)
        index = self.tone.findData(self.pitch.value())
        self.tone.setCurrentIndex(index if index >= 0 else self.tone.count() - 1)
        self.tone.blockSignals(False)

    def set_tone(self, *_):
        value = self.tone.currentData()
        if value is not None:
            self.pitch.setValue(value)

    def model_hint(self, *_):
        self.voice.setToolTip(self.voice.currentText())
        warm = self.owner.local_tts_session.ready
        self.release.setEnabled(warm and not self.running)
        if not is_local_voice(self.voice.currentData()):
            self.status.setText('Edge TTS cần mạng. Bấm Nghe thử để nghe câu bạn nhập.')
        elif warm:
            self.status.setText('VieNeu đã có trong RAM; chọn giọng khác dùng chung mô hình này. Âm nghe thử đã tạo cũng được dùng lại.')
        else:
            self.status.setText('VieNeu: lần đầu cần tải / nạp mô hình. Các lần đổi giọng sau giữ mô hình trong RAM đến khi đóng app hoặc giải phóng RAM.')

    def set_running(self, value):
        self.running = value
        for widget in (self.filters, self.voice, self.tone, self.pitch, self.rate, self.text, self.play, self.apply):
            widget.setEnabled(not value)
        self.stop.setText('Hủy tạo giọng' if value else 'Dừng nghe')
        self.release.setEnabled(not value and self.owner.local_tts_session.ready)

    def listen(self):
        if self.running or self.owner.busy:
            return
        text = self.text.toPlainText()
        if not text.strip():
            self.status.setText('Hãy nhập câu cần nghe thử.')
            return
        if len(text) > 500:
            self.status.setText('Nghe thử tối đa 500 ký tự.')
            return
        voice, rate, pitch = self.voice.currentData(), self.rate.value(), self.pitch.value()
        self.player.stop()
        self.set_running(True)
        cache = self.owner.cache_root / 'voice-samples'

        def done(result):
            self.set_running(False)
            if self.close_after_job:
                self.reject()
                return
            self.player.setPlaybackRate(1)
            self.player.setSource(QUrl.fromLocalFile(str(Path(result['path']).resolve())))
            self.player.play()
            self.status.setText(f'Đang nghe thử · {result["duration"]:.1f} giây. Có thể chọn giọng khác và bấm Nghe thử.')

        def failed(message):
            self.set_running(False)
            if self.close_after_job:
                self.reject()
            else:
                self.status.setText(message)

        self.owner.start_job(lambda c, r: preview_voice(text, voice, rate, pitch, cache, c, r,
                                                      local_session=self.owner.local_tts_session),
                             done, 'Nghe thử giọng đọc', failed=failed)
        if self.owner.worker:self.owner.worker.progress.connect(lambda _, message: self.status.setText(message))

    def stop_or_cancel(self):
        self.player.stop()
        if self.running:
            self.owner.cancel_job()
            self.status.setText('Đang hủy tạo giọng…')

    def release_model(self):
        if self.running:
            return
        self.owner.release_local_tts()
        self.model_hint()

    def apply_to_project(self):
        if self.running:
            return
        owner = self.owner
        owner.push_undo()
        owner.p.voice, owner.p.tts_rate, owner.p.tts_pitch = self.voice.currentData(), self.rate.value(), self.pitch.value()
        owner.load_controls()
        owner.changed()
        self.accept()

    def reject(self):
        self.player.stop()
        if self.running:
            self.close_after_job = True
            self.stop_or_cancel()
            return
        super().reject()

    def done(self, result):
        if self.running:
            self.reject()
            return
        self.player.stop()
        super().done(result)

    def closeEvent(self, event):
        if self.running:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)

