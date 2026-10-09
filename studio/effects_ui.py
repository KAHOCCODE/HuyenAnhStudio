"""Video composition dialog; the editor keeps source coordinates for masking."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QComboBox, QCheckBox, QDoubleSpinBox, QSpinBox, QPushButton,
    QLabel, QColorDialog, QDialogButtonBox, QMessageBox, QScrollArea, QWidget)
from PySide6.QtGui import QColor
from .video_effects import settings


class EffectsDialog(QDialog):
    def __init__(self, parent, value):
        super().__init__(parent)
        self.setWindowTitle('Khung hình & màu sắc')
        self.resize(780, 730)
        self.values = settings(value)
        self.controls = {}
        self.preview_requested = False
        root = QVBoxLayout(self)
        self.enabled = QCheckBox('Bật tùy chỉnh khung hình và hiệu ứng khi xuất')
        self.enabled.setChecked(self.values['enabled'])
        root.addWidget(self.enabled)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        body = QWidget(); columns = QHBoxLayout(body)
        self.body = body
        scroll.setWidget(body); root.addWidget(scroll)
        left = QGroupBox('Khung hình'); lf = QFormLayout(left)
        right = QGroupBox('Màu sắc & hiệu ứng'); rf = QFormLayout(right)
        columns.addWidget(left); columns.addWidget(right)
        for form in (lf, rf):
            form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        def combo(form, key, label, choices):
            widget = QComboBox()
            for text, data in choices: widget.addItem(text, data)
            widget.setCurrentIndex(widget.findData(self.values[key]))
            form.addRow(label, widget); self.controls[key] = widget
            return widget
        def number(form, key, label, low, high, step=.01, integer=False):
            widget = QSpinBox() if integer else QDoubleSpinBox()
            widget.setRange(low, high); widget.setSingleStep(step)
            if not integer: widget.setDecimals(2)
            widget.setValue(self.values[key])
            form.addRow(label, widget); self.controls[key] = widget
            return widget
        def color(form, key, label):
            button = QPushButton(self.values[key])
            def pick():
                c = QColorDialog.getColor(QColor(button.text()), self)
                if c.isValid(): button.setText(c.name())
            button.clicked.connect(pick); form.addRow(label, button)
            self.controls[key] = button
        size = combo(lf, 'size', 'Kích thước xuất', [
            ('Giữ kích thước gốc', 'source'), ('16:9 · 1920 × 1080', 'landscape'),
            ('9:16 · 1080 × 1920', 'portrait'), ('1:1 · 1080 × 1080', 'square'),
            ('4:3 · 1440 × 1080', 'classic'), ('Tự nhập kích thước', 'custom')])
        width = number(lf, 'width', 'Rộng (px)', 64, 7680, 2, True)
        height = number(lf, 'height', 'Cao (px)', 64, 7680, 2, True)
        layout = combo(lf, 'layout', 'Cách đặt video', [
            ('Lấp đầy / cắt mép', 'crop'), ('Giữ đủ hình / nền màu', 'fit'),
            ('Nền video làm mờ', 'blur'), ('Nền mờ + viền động', 'frame')])
        zoom = number(lf, 'zoom', 'Phóng to ×', 1, 3, .05)
        presets = QHBoxLayout()
        for text, value in [('100%', 1), ('110%', 1.1), ('115%', 1.15)]:
            b = QPushButton(text); b.clicked.connect(lambda checked=False, z=value: zoom.setValue(z)); presets.addWidget(b)
        lf.addRow('Zoom nhanh', presets)
        number(lf, 'x', 'Bố cục ngang (%)', 0, 100, 1)
        number(lf, 'y', 'Bố cục dọc (%)', 0, 100, 1)
        flip = QCheckBox('Lật gương ngang'); flip.setChecked(self.values['flip'])
        lf.addRow(flip); self.controls['flip'] = flip
        hint = QLabel('Lật ngang cũng lật chữ có sẵn trong phim. Phụ đề Việt do ứng dụng thêm vẫn đọc bình thường.'); hint.setWordWrap(True); lf.addRow(hint)
        number(lf, 'inset', 'Khoảng nền mỗi bên (%)', 0, 30, 1)
        number(lf, 'blur', 'Độ mờ nền', 1, 60, 1)
        color(lf, 'background', 'Màu nền')
        color(lf, 'border', 'Màu viền động')
        number(rf, 'saturation', 'Độ bão hòa ×', 0, 2, .05)
        number(rf, 'contrast', 'Tương phản ×', .5, 1.5, .05)
        number(rf, 'brightness', 'Độ sáng', -.2, .2, .01)
        number(rf, 'temperature', 'Tông lạnh − / ấm +', -1, 1, .05)
        combo(rf, 'effect', 'Lớp phủ', [('Không', 'none'), ('Sương sáng nhẹ', 'haze'),
                                     ('Bụi sáng chuyển động', 'dust'), ('Ánh sáng chuyển động', 'light')])
        number(rf, 'opacity', 'Cường độ lớp phủ (0–0,3)', 0, .3, .01)
        note = QLabel('100% / X=50 / Y=50 là bố cục giữa. Zoom 110% và 115% cắt bớt mép ảnh.\n\nKhung chỉnh vùng che vẫn dùng hình gốc. Bấm “Xem thử 10 giây” để kiểm tra đúng khung hình, màu sắc và chuyển động sau khi xuất.'); note.setWordWrap(True); rf.addRow(note)
        def update():
            custom = size.currentData() == 'custom'
            width.setEnabled(custom); height.setEnabled(custom)
            mode = layout.currentData()
            for key in ('inset', 'blur'): self.controls[key].setEnabled(mode in ('blur', 'frame'))
            self.controls['background'].setEnabled(mode == 'fit')
            self.controls['border'].setEnabled(mode == 'frame')
        size.currentIndexChanged.connect(update); layout.currentIndexChanged.connect(update); update()
        self.enabled.toggled.connect(body.setEnabled); body.setEnabled(self.enabled.isChecked())
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Áp dụng')
        buttons.button(QDialogButtonBox.Cancel).setText('Hủy')
        preview = buttons.addButton('Xem thử 10 giây', QDialogButtonBox.ActionRole)
        preview.clicked.connect(lambda: self.apply(True))
        buttons.accepted.connect(lambda: self.apply(False)); buttons.rejected.connect(self.reject)
        reset = buttons.addButton('Đặt lại', QDialogButtonBox.ResetRole)
        def reset_values():
            defaults = settings({})
            self.enabled.setChecked(False)
            for key, widget in self.controls.items():
                value = defaults[key]
                if isinstance(widget, QComboBox): widget.setCurrentIndex(widget.findData(value))
                elif isinstance(widget, QCheckBox): widget.setChecked(value)
                elif isinstance(widget, QPushButton): widget.setText(value)
                else: widget.setValue(value)
        reset.clicked.connect(reset_values)
        root.addWidget(buttons)

    def apply(self, preview):
        result = dict(enabled=self.enabled.isChecked())
        for key, widget in self.controls.items():
            if isinstance(widget, QComboBox): result[key] = widget.currentData()
            elif isinstance(widget, QCheckBox): result[key] = widget.isChecked()
            elif isinstance(widget, QPushButton): result[key] = widget.text()
            else: result[key] = widget.value()
        try: self.values = settings(result)
        except ValueError as e:
            QMessageBox.warning(self, 'Thiết lập chưa hợp lệ', str(e)); return
        self.preview_requested = preview
        self.accept()
