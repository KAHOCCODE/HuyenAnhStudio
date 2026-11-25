"""Catalogue filters that preserve the selected voice until an explicit choice."""
from PySide6.QtWidgets import QWidget, QComboBox, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy

from .voices import VOICES, matching_voices


class VoiceFilters(QWidget):
    def __init__(self, combo, parent=None, allow_default=False):
        super().__init__(parent)
        self.combo = combo
        self.allow_default = allow_default
        self.selected = combo.currentData() or ''
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        row = QHBoxLayout()
        self.gender = QComboBox()
        self.gender.setObjectName('voiceGenderFilter')
        for label, value in [('Nam/nữ · Tất cả', ''), ('Giọng nam', 'male'), ('Giọng nữ', 'female')]:
            self.gender.addItem(label, value)
        self.region = QComboBox()
        self.region.setObjectName('voiceRegionFilter')
        for label, value in [('Vùng · Tất cả', ''), ('Miền Bắc', 'north'), ('Miền Trung', 'central'),
                             ('Miền Nam', 'south'), ('Chưa rõ miền', 'unknown')]:
            self.region.addItem(label, value)
        for picker in (self.gender, self.region):
            picker.setMinimumWidth(80)
            picker.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            row.addWidget(picker, 1)
            picker.currentIndexChanged.connect(self.rebuild)
        layout.addLayout(row)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setObjectName('muted')
        layout.addWidget(self.summary)
        self.combo.currentIndexChanged.connect(self.remember_selection)
        self.rebuild()

    def remember_selection(self, *_):
        value = self.combo.currentData()
        if value is not None:
            self.selected = value
            self.rebuild()

    def select_voice(self, voice):
        self.selected = voice or ''
        self.rebuild()

    def rebuild(self, *_):
        matches = matching_voices(self.gender.currentData(), self.region.currentData())
        voice = self.selected
        selected_outside = bool(voice) and voice not in {value for _, value in matches}
        blocked = self.combo.blockSignals(True)
        try:
            self.combo.clear()
            if self.allow_default:
                self.combo.addItem('Giọng mặc định', '')
            if selected_outside:
                label = next((label for label, value in VOICES.items() if value == voice), voice)
                self.combo.addItem('Đang chọn · ' + label + ' (ngoài bộ lọc)', voice)
                if matches:
                    self.combo.insertSeparator(self.combo.count())
            for label, value in matches:
                self.combo.addItem(label, value)
            self.combo.setCurrentIndex(self.combo.findData(voice))
        finally:
            self.combo.blockSignals(blocked)
        self.summary.setText((f'{len(matches)} giọng phù hợp' if matches else 'Không có giọng phù hợp')
                             + (' · giữ giọng đang chọn' if selected_outside else ''))
        self.summary.setToolTip('Lọc danh sách không tự đổi giọng. Giọng hiện tại nằm ngoài bộ lọc vẫn được giữ cho đến khi bạn chọn giọng khác.'
                                if selected_outside else 'Giọng Edge chưa có nhãn vùng miền, nằm trong nhóm Chưa rõ miền.')
        self.combo.setToolTip(self.combo.currentText())
