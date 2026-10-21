"""Docked editor for output-space channel branding and artwork."""
import copy
from PySide6.QtCore import Signal,Qt
from PySide6.QtGui import QColor,QFont
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,
    QListWidget,QScrollArea,QCheckBox,QComboBox,QDoubleSpinBox,QPlainTextEdit,QLineEdit,
    QFontComboBox,QColorDialog,QFileDialog,QGroupBox,QMessageBox)
from .composition import new_layer,validate_layer,sidebar_settings,TEXT_PRESETS,ICONS


class LayersPanel(QWidget):
    compositionChanged=Signal(list,dict)
    selectionChanged=Signal()
    def __init__(self,project,parent=None):
        super().__init__(parent);self.duration=project.duration;self.layers=copy.deepcopy(project.overlays);self.sidebar=sidebar_settings(project.sidebar);self.loading=True
        self.setMinimumWidth(315);root=QVBoxLayout(self)
        note=QLabel('Che sub gốc → lật hình → thêm chữ / logo → phụ đề Việt.\nCác lớp ở đây luôn đúng chiều. Kéo lớp trên preview để di chuyển; kéo góc để đổi kích thước.');note.setWordWrap(True);root.addWidget(note)
        row=QHBoxLayout()
        for text,kind in [('＋ Chữ','text'),('＋ Logo','image'),('＋ Biểu tượng','icon')]:
            b=QPushButton(text);b.clicked.connect(lambda checked=False,k=kind:self.add(k));row.addWidget(b)
        root.addLayout(row)
        b=QPushButton('＋ Thông báo có vạch đỏ · như ảnh mẫu');b.clicked.connect(lambda:self.add('text','notice'));root.addWidget(b)
        self.list=QListWidget();self.list.setMaximumHeight(135);self.list.currentRowChanged.connect(self.select);root.addWidget(self.list)
        row=QHBoxLayout()
        for text,fn in [('↑',lambda:self.reorder(-1)),('↓',lambda:self.reorder(1)),('Nhân đôi',self.duplicate),('Xóa',self.remove)]:
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        root.addLayout(row)
        scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();vertical=QVBoxLayout(body);scroll.setWidget(body);root.addWidget(scroll,1)
        bar=QGroupBox('Dải bên để đặt chữ / logo');form=QFormLayout(bar);vertical.addWidget(bar)
        self.bar_on=QCheckBox('Chừa dải bên trong khung xuất');self.bar_on.setChecked(self.sidebar['enabled']);form.addRow(self.bar_on)
        self.bar_side=QComboBox();self.bar_side.addItem('Bên phải','right');self.bar_side.addItem('Bên trái','left');self.bar_side.setCurrentIndex(self.bar_side.findData(self.sidebar['side']));form.addRow('Vị trí',self.bar_side)
        self.bar_width=QDoubleSpinBox();self.bar_width.setRange(10,40);self.bar_width.setSuffix(' %');self.bar_width.setValue(self.sidebar['width']);form.addRow('Độ rộng',self.bar_width)
        self.bar_color=QPushButton(self.sidebar['color']);self.bar_color.clicked.connect(lambda:self.pick(self.bar_color,self.update_sidebar));form.addRow('Màu nền',self.bar_color)
        b=QPushButton('Đặt lớp đang chọn vào dải bên');b.clicked.connect(self.place_in_sidebar);form.addRow(b)
        for widget,signal in [(self.bar_on,'toggled'),(self.bar_side,'currentIndexChanged'),(self.bar_width,'valueChanged')]:getattr(widget,signal).connect(self.update_sidebar)
        self.editor=QGroupBox('Lớp đang chọn · lớp dưới cùng nằm trên hình');form=QFormLayout(self.editor);vertical.addWidget(self.editor);vertical.addStretch();self.controls={}
        def add(key,label,widget):self.controls[key]=widget;form.addRow(label,widget);return widget
        add('name','Tên lớp',QLineEdit());add('enabled','',QCheckBox('Hiện lớp này'))
        preset=QComboBox()
        for label,key in [('Chọn mẫu chữ…',''),('Trắng có viền','clean'),('Thông báo vạch đỏ','notice'),('Vàng sang trọng','gold'),('Nhãn nền tối','label'),('Xanh ngọc','neon')]:preset.addItem(label,key)
        preset.currentIndexChanged.connect(lambda:self.apply_preset(preset.currentData()));form.addRow('Mẫu trang trí',preset)
        text=add('text','Nội dung',QPlainTextEdit());text.setMaximumHeight(110)
        self.logo_label=QLabel();self.logo_label.setWordWrap(True);form.addRow(self.logo_label)
        self.logo_button=QPushButton('Chọn / thay ảnh logo');self.logo_button.clicked.connect(self.replace_logo);form.addRow(self.logo_button)
        icon=QComboBox()
        for key,label in ICONS.items():icon.addItem(label,key)
        add('icon','Biểu tượng',icon)
        add('font','Phông chữ',QFontComboBox())
        for key,label,lo,hi in [('size','Cỡ chữ / 1080p',8,240),('x','X (%)',0,99.9),('y','Y (%)',0,99.9),('w','Rộng (%)',.1,100),('h','Cao (%)',.1,100),('start','Từ giây nguồn',0,max(1,self.duration)),('end','Đến giây nguồn',.001,max(1,self.duration)),('outline','Độ dày viền',0,12),('shadow','Bóng chữ',0,16),('opacity','Độ hiện',0,1),('background_opacity','Độ hiện nền',0,1),('radius','Bo góc / 1080p',0,60)]:
            spin=QDoubleSpinBox();spin.setRange(lo,hi);spin.setDecimals(2 if key not in ('start','end') else 3);spin.setSingleStep(.05 if hi==1 else 1);add(key,label,spin)
        b=QPushButton('Hiện suốt video');b.clicked.connect(self.full_duration);form.addRow(b)
        align=QComboBox()
        for name,key in [('Trái','left'),('Giữa','center'),('Phải','right')]:align.addItem(name,key)
        add('align','Căn chữ',align)
        for key,label in [('bold','In đậm'),('background','Nền sau chữ'),('accent','Vạch dọc cạnh chữ')]:add(key,'',QCheckBox(label))
        for key,label in [('color','Màu chữ / biểu tượng'),('outline_color','Màu viền'),('background_color','Màu nền'),('accent_color','Màu vạch dọc')]:
            b=QPushButton();b.clicked.connect(lambda checked=False,button=b:self.pick(button,self.edit));add(key,label,b)
        for key,widget in self.controls.items():
            if isinstance(widget,QFontComboBox):widget.currentFontChanged.connect(self.edit)
            elif isinstance(widget,QComboBox):widget.currentIndexChanged.connect(self.edit)
            elif isinstance(widget,QCheckBox):widget.toggled.connect(self.edit)
            elif isinstance(widget,QDoubleSpinBox):widget.valueChanged.connect(self.edit)
            elif isinstance(widget,(QLineEdit,QPlainTextEdit)):widget.textChanged.connect(self.edit)
        self.loading=False;self.refill()

    @property
    def selected(self):
        i=self.list.currentRow();return self.layers[i] if 0<=i<len(self.layers) else None

    def refill(self,index=0):
        self.loading=True;self.list.clear()
        for v in self.layers:self.list.addItem(('● ' if v['enabled'] else '○ ')+v['name'])
        self.loading=False;self.list.setCurrentRow(min(index,len(self.layers)-1));self.select()

    def select(self,*args):
        if self.loading:return
        self.loading=True;v=self.selected;self.editor.setEnabled(v is not None)
        if v:
            for key,widget in self.controls.items():
                value=v[key]
                if isinstance(widget,QFontComboBox):widget.setCurrentFont(QFont(value))
                elif isinstance(widget,QComboBox):widget.setCurrentIndex(widget.findData(value))
                elif isinstance(widget,QCheckBox):widget.setChecked(value)
                elif isinstance(widget,QDoubleSpinBox):widget.setValue(value)
                elif isinstance(widget,QPlainTextEdit):widget.setPlainText(value)
                else:widget.setText(value)
            self.logo_label.setText(v['image']);self.logo_label.setVisible(v['kind']=='image');self.logo_button.setVisible(v['kind']=='image')
        self.loading=False;self.selectionChanged.emit()

    def edit(self,*args):
        if self.loading or not self.selected:return
        v=copy.deepcopy(self.selected)
        for key,widget in self.controls.items():
            if isinstance(widget,QFontComboBox):value=widget.currentFont().family()
            elif isinstance(widget,QComboBox):value=widget.currentData()
            elif isinstance(widget,QCheckBox):value=widget.isChecked()
            elif isinstance(widget,QDoubleSpinBox):value=widget.value()
            elif isinstance(widget,QPlainTextEdit):value=widget.toPlainText()
            else:value=widget.text()
            v[key]=value
        v['w']=min(v['w'],100-v['x']);v['h']=min(v['h'],100-v['y'])
        # Keep unfinished time entries in the controls, apply only valid ranges.
        try:validate_layer(v,self.duration)
        except ValueError:return
        self.loading=True;self.controls['w'].setValue(v['w']);self.controls['h'].setValue(v['h']);self.loading=False
        self.layers[self.list.currentRow()]=v
        self.list.currentItem().setText(('● ' if v['enabled'] else '○ ')+v['name']);self.emit()

    def emit(self):self.compositionChanged.emit(copy.deepcopy(self.layers),dict(self.sidebar));self.selectionChanged.emit()
    def pick(self,button,callback):
        c=QColorDialog.getColor(QColor(button.text()),self)
        if c.isValid():button.setText(c.name());callback()
    def add(self,kind,preset='clean'):
        if len(self.layers)>=40:QMessageBox.warning(self,'Số lớp','Tối đa 40 lớp.');return
        v=new_layer(kind,self.duration,preset)
        if kind=='image':
            path,_=QFileDialog.getOpenFileName(self,'Chọn ảnh logo PNG / JPG','','Ảnh (*.png *.jpg *.jpeg *.webp *.bmp)')
            if not path:return
            v['image']=path
        self.layers.append(v);self.refill(len(self.layers)-1);self.emit()
    def remove(self):
        i=self.list.currentRow()
        if self.selected:self.layers.pop(i);self.refill(max(0,i-1));self.emit()
    def duplicate(self):
        if self.selected and len(self.layers)<40:
            from uuid import uuid4
            v=copy.deepcopy(self.selected);v.update(id=uuid4().hex[:12],name=v['name']+' · bản sao');self.layers.append(v);self.refill(len(self.layers)-1);self.emit()
    def reorder(self,delta):
        i=self.list.currentRow();j=i+delta
        if 0<=j<len(self.layers):self.layers[i],self.layers[j]=self.layers[j],self.layers[i];self.refill(j);self.emit()
    def replace_logo(self):
        if not self.selected:return
        path,_=QFileDialog.getOpenFileName(self,'Chọn logo','','Ảnh (*.png *.jpg *.jpeg *.webp *.bmp)')
        if path:self.selected['image']=path;self.select();self.emit()
    def apply_preset(self,key):
        if key and self.selected:self.selected.update(TEXT_PRESETS[key]);self.select();self.emit()
    def full_duration(self):
        if self.selected:self.selected.update(start=0.,end=max(.001,self.duration));self.select();self.emit()
    def update_sidebar(self,*args):
        if self.loading:return
        self.sidebar=dict(enabled=self.bar_on.isChecked(),side=self.bar_side.currentData(),width=self.bar_width.value(),color=self.bar_color.text());self.emit()
    def place_in_sidebar(self):
        if not self.selected:return
        self.bar_on.setChecked(True);self.update_sidebar()
        width=self.sidebar['width'];self.selected.update(x=100-width+2 if self.sidebar['side']=='right' else 2.,w=width-4,y=6.,h=35.)
        self.select();self.emit()
    def set_geometry(self,values):
        if self.selected:self.selected.update(values);self.select();self.emit()
    def load_project(self,p):
        same_duration=self.duration==p.duration;self.duration=p.duration
        if same_duration and self.layers==p.overlays and self.sidebar==sidebar_settings(p.sidebar):return
        i=self.list.currentRow();self.layers=copy.deepcopy(p.overlays);self.sidebar=sidebar_settings(p.sidebar);self.loading=True
        self.bar_on.setChecked(self.sidebar['enabled']);self.bar_side.setCurrentIndex(self.bar_side.findData(self.sidebar['side']));self.bar_width.setValue(self.sidebar['width']);self.bar_color.setText(self.sidebar['color'])
        for key in ('start','end'):self.controls[key].setMaximum(max(1,self.duration))
        self.loading=False;self.refill(i)
