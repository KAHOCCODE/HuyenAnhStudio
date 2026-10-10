"""Video composition dialog; the editor keeps source coordinates for masking."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QComboBox, QCheckBox, QDoubleSpinBox, QSpinBox, QPushButton,
    QLabel, QColorDialog, QDialogButtonBox, QMessageBox, QScrollArea, QWidget, QSplitter)
from PySide6.QtGui import QColor
from .video_effects import settings
from .frame_editor import FrameEditor


class EffectsDialog(QDialog):
    def __init__(self, parent, value):
        super().__init__(parent)
        self.setWindowTitle('Khung hình & màu sắc')
        screen = self.screen().availableGeometry()
        self.resize(min(1120, screen.width()-40), min(720, screen.height()-80))
        self._loading = True
        self.values = settings(value)
        self.controls = {}
        self.preview_requested = False
        self.full_export_requested = False
        root = QVBoxLayout(self)
        self.enabled = QCheckBox('Bật tùy chỉnh khung hình và hiệu ứng khi xuất')
        self.enabled.setChecked(self.values['enabled'])
        root.addWidget(self.enabled)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)
        visual = QWidget(); visual_layout = QVBoxLayout(visual)
        visual_layout.setContentsMargins(0, 0, 8, 0)
        hint = QLabel('Kéo hình để đổi bố cục · Cuộn chuột / kéo góc để zoom · Nhấp đúp để căn giữa')
        hint.setWordWrap(True); visual_layout.addWidget(hint)
        frame = getattr(getattr(getattr(parent, 'preview', None), 'overlay', None), 'frame', None)
        project = getattr(parent, 'p', None)
        source_size = (project.width, project.height) if project else (1920, 1080)
        self.canvas = FrameEditor(frame, source_size, self)
        visual_layout.addWidget(self.canvas, 1)
        self.state_label = QLabel(); self.state_label.setWordWrap(True); visual_layout.addWidget(self.state_label)
        preview_note = QLabel('Khung này dùng ảnh tại vị trí đang xem để chỉnh bố cục. Nền mờ là minh họa nhanh; màu sắc, lớp phủ, phụ đề và chuyển động xem bằng “Xem thử 10 giây”.')
        preview_note.setWordWrap(True); visual_layout.addWidget(preview_note)
        split.addWidget(visual)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(300)
        body = QWidget(); columns = QVBoxLayout(body)
        self.body = body
        scroll.setWidget(body); split.addWidget(scroll); split.setSizes([660, 400])
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
                if c.isValid():
                    button.setText(c.name()); self.control_changed()
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
        # Keep inputs usable even when effects are off. Editing opts in.
        self.enabled.toggled.connect(self.refresh_canvas)
        self.canvas.edited.connect(self.direct_edit)
        for widget in self.controls.values():
            if isinstance(widget, QComboBox): widget.currentIndexChanged.connect(self.control_changed)
            elif isinstance(widget, QCheckBox): widget.toggled.connect(self.control_changed)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)): widget.valueChanged.connect(self.control_changed)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Lưu thiết lập')
        buttons.button(QDialogButtonBox.Cancel).setText('Hủy')
        full = QPushButton('Áp dụng và xuất toàn bộ video')
        full.setMinimumHeight(36)
        full.clicked.connect(self.export_full)
        root.addWidget(full)
        preview = buttons.addButton('Xem thử 10 giây', QDialogButtonBox.ActionRole)
        preview.clicked.connect(lambda: self.apply(True))
        buttons.accepted.connect(lambda: self.apply(False)); buttons.rejected.connect(self.reject)
        reset = buttons.addButton('Đặt lại', QDialogButtonBox.ResetRole)
        def reset_values():
            self._loading = True
            defaults = settings({})
            self.enabled.setChecked(False)
            for key, widget in self.controls.items():
                value = defaults[key]
                if isinstance(widget, QComboBox): widget.setCurrentIndex(widget.findData(value))
                elif isinstance(widget, QCheckBox): widget.setChecked(value)
                elif isinstance(widget, QPushButton): widget.setText(value)
                else: widget.setValue(value)
            self._loading = False
            self.refresh_canvas()
        reset.clicked.connect(reset_values)
        root.addWidget(buttons)
        self._loading = False
        self.refresh_canvas()

    def collect_values(self):
        result = dict(enabled=self.enabled.isChecked())
        for key, widget in self.controls.items():
            if isinstance(widget, QComboBox): result[key] = widget.currentData()
            elif isinstance(widget, QCheckBox): result[key] = widget.isChecked()
            elif isinstance(widget, QPushButton): result[key] = widget.text()
            else: result[key] = widget.value()
        return result

    def refresh_canvas(self, *args):
        self.canvas.set_values(self.collect_values())
        self.state_label.setText('Đang bật · Bấm “Áp dụng và xuất toàn bộ video” để tạo bản hoàn chỉnh.' if self.enabled.isChecked()
                                else 'Đang tắt · Chỉnh hình hoặc thay đổi thông số để tự bật.')

    def control_changed(self, *args):
        if self._loading: return
        self.enabled.setChecked(True)
        self.refresh_canvas()

    def direct_edit(self, x, y, zoom):
        self._loading = True
        for key, value in [('x', x), ('y', y), ('zoom', zoom)]:
            self.controls[key].setValue(value)
        self._loading = False
        self.enabled.setChecked(True)
        self.refresh_canvas()

    def export_full(self):
        self.full_export_requested = True
        self.apply(False)
        if self.result() != QDialog.Accepted:
            self.full_export_requested = False

    def apply(self, preview):
        result = self.collect_values()
        try: self.values = settings(result)
        except ValueError as e:
            QMessageBox.warning(self, 'Thiết lập chưa hợp lệ', str(e)); return
        self.preview_requested = preview
        self.accept()
