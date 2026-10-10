"""Play a completed export without applying the source project's filters twice."""
from pathlib import Path
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget


class ResultPlayer(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Video hoàn chỉnh · '+Path(path).name)
        screen = self.screen().availableGeometry()
        self.resize(min(1000, screen.width()-40), min(680, screen.height()-80))
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self); self.audio.setVolume(1)
        self.player.setAudioOutput(self.audio)
        layout = QVBoxLayout(self)
        label = QLabel('Bản đã áp dụng khung, màu và hiệu ứng cho toàn bộ video. Dự án nguồn vẫn được giữ để chỉnh tiếp.')
        label.setWordWrap(True); layout.addWidget(label)
        video = QVideoWidget(); layout.addWidget(video, 1); self.player.setVideoOutput(video)
        self.slider = QSlider(Qt.Horizontal); layout.addWidget(self.slider)
        self.time = QLabel('00:00 / 00:00'); layout.addWidget(self.time)
        self.player.durationChanged.connect(lambda n:self.slider.setRange(0,n))
        self.player.positionChanged.connect(self.position)
        self.slider.sliderMoved.connect(self.player.setPosition)
        buttons = QHBoxLayout(); layout.addLayout(buttons)
        self.play = QPushButton('Phát / Tạm dừng'); self.play.clicked.connect(self.toggle); buttons.addWidget(self.play)
        external = QPushButton('Mở bằng trình phát của máy'); buttons.addWidget(external)
        external.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
        close = QPushButton('Về chỉnh sửa'); close.clicked.connect(self.accept); buttons.addWidget(close)
        self.error_label = QLabel(); self.error_label.setWordWrap(True); layout.addWidget(self.error_label)
        self.player.errorOccurred.connect(lambda *args:self.error_label.setText('Không phát được trong ứng dụng: '+self.player.errorString()+'. Bạn có thể mở bằng trình phát của máy.'))
        self.player.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))
        self.player.play()
        self.finished.connect(lambda _:self.player.stop())

    def position(self, ms):
        if not self.slider.isSliderDown(): self.slider.setValue(ms)
        def stamp(n):
            s=max(0,n//1000); return f'{s//3600:02}:{s//60%60:02}:{s%60:02}'
        self.time.setText(stamp(ms)+' / '+stamp(self.player.duration()))

    def toggle(self):
        if self.player.playbackState()==QMediaPlayer.PlayingState:self.player.pause()
        else:self.player.play()
