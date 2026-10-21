"""One persistent inspector; each editing stage owns its controls and actions."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,
    QCheckBox,QComboBox,QScrollArea,QStackedWidget,QTabWidget,QMenu,QGroupBox,QSizePolicy)

STAGES=('1 · Nguồn','2 · Hình ảnh','3 · Chữ / logo','4 · Sub và giọng','5 · Xuất video')
HINTS=(
    'Chọn video để bắt đầu. Thiết lập sẽ được lưu trong cùng dự án.',
    'Che chữ trên hình nguồn trước; lật và đổi khung được xem ở tab Khung & màu.',
    'Các lớp chữ, logo và biểu tượng luôn đúng chiều trên khung xuất.',
    'Nhập SRT, chỉnh mẫu chữ; chỉ tạo giọng đọc nếu bạn cần lồng tiếng.',
    'Kiểm tra kích thước, thời lượng và âm thanh; xem thử trước khi xuất toàn bộ.')


class Foldout(QWidget):
    def __init__(self,title,parent=None):
        super().__init__(parent);layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.toggle=QPushButton('▸ '+title);self.toggle.setCheckable(True);layout.addWidget(self.toggle)
        self.body=QWidget();self.body_layout=QVBoxLayout(self.body);self.body_layout.setContentsMargins(0,6,0,6);layout.addWidget(self.body);self.body.hide()
        self.toggle.toggled.connect(lambda on:(self.body.setVisible(on),self.toggle.setText(('▾ ' if on else '▸ ')+title)))


def scroll(widget):
    area=QScrollArea();area.setWidgetResizable(True);area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);area.setWidget(widget);return area


def fold_rows(group,keep,title='Nâng cao'):
    """Move complete form rows, preserving widgets and their existing signal wiring."""
    form=group.layout();advanced=Foldout(title);details=QWidget();rows=QFormLayout(details)
    rows.setRowWrapPolicy(QFormLayout.WrapLongRows);rows.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    for i in reversed(range(form.rowCount())):
        field=form.itemAt(i,QFormLayout.FieldRole) or form.itemAt(i,QFormLayout.SpanningRole)
        if field and field.widget() in keep:continue
        row=form.takeRow(i);label=row.labelItem;value=row.fieldItem
        if not value:continue
        # takeRow keeps ownership; inserting at zero restores the original order.
        if label and label.widget():
            if value.widget():rows.insertRow(0,label.widget(),value.widget())
            elif value.layout():rows.insertRow(0,label.widget(),value.layout())
        elif value.widget():rows.insertRow(0,value.widget())
        elif value.layout():rows.insertRow(0,value.layout())
    advanced.body_layout.addWidget(details);form.addRow(advanced)
    return advanced


def install(w,outer,props,stylebox,maskbox,speedbox,voicebox,exportbox):
    # The former all-settings column is replaced by one shared stage stack.
    groups={stylebox,maskbox,speedbox,voicebox,exportbox}
    while props.count():
        item=props.takeAt(0);widget=item.widget()
        if widget:
            widget.setParent(None)
            if widget not in groups and widget is not w.effects_summary:widget.deleteLater()
    w.workflow_stack=QStackedWidget();props.addWidget(w.workflow_stack)
    w.workflow_bar=QWidget();nav=QHBoxLayout(w.workflow_bar);nav.setContentsMargins(0,0,0,0);w.stage_buttons=[]
    for index,name in enumerate(STAGES):
        button=QPushButton(name);button.setObjectName('workflowStep');button.setCheckable(True);button.clicked.connect(lambda checked=False,i=index:w.go_stage(i));nav.addWidget(button);w.stage_buttons.append(button)
    outer.insertWidget(1,w.workflow_bar)
    source=QWidget();layout=QVBoxLayout(source);layout.addWidget(QLabel('VIDEO NGUỒN'))
    w.import_video_btn=w.button('Chọn / thay video…',w.import_video,True);layout.addWidget(w.import_video_btn)
    layout.addWidget(w.media_label);layout.addWidget(w.media_details)
    note=QLabel('Bạn có thể chỉ chỉnh hình và xuất video. Phụ đề, logo và giọng đọc là các bước tùy chọn.');note.setWordWrap(True);layout.addWidget(note)
    advanced=Foldout('Khắc phục khi xem bị giật / mất tiếng')
    for label,fn in [('Tạo bản xem nhẹ toàn phim…',w.make_proxy),('Dùng bộ phát CPU',w.switch_cpu),('Chọn lại loa / tai nghe',w.restore_audio)]:advanced.body_layout.addWidget(w.button(label,fn))
    layout.addWidget(advanced);layout.addStretch();w.workflow_stack.addWidget(source)
    fold_rows(maskbox,{w.mask_on,w.mask_mode,w.mask_preset,w.mask_edit,w.mask_strength},'Vị trí, màu và nhiều vùng che')
    w.picture_tabs=QTabWidget();w.picture_tabs.addTab(scroll(maskbox),'Che sub gốc')
    w.effects_page=QWidget();w.effects_layout=QVBoxLayout(w.effects_page);w.effects_layout.setContentsMargins(0,0,0,0)
    w.picture_tabs.addTab(w.effects_page,'Khung và màu');w.picture_tabs.currentChanged.connect(w.picture_tab_changed)
    w.workflow_stack.addWidget(w.picture_tabs)
    w.layers_page=QWidget();w.layers_layout=QVBoxLayout(w.layers_page);w.layers_layout.setContentsMargins(0,0,0,0);w.workflow_stack.addWidget(w.layers_page)
    fold_rows(stylebox,{w.preset,w.font_picker,w.font_size,w.color},'Viền, nền, vị trí và hiệu ứng chữ')
    w.subtitle_tabs=QTabWidget();w.subtitle_tabs.addTab(scroll(stylebox),'Kiểu phụ đề');w.subtitle_tabs.addTab(scroll(voicebox),'Âm thanh / giọng đọc');w.workflow_stack.addWidget(w.subtitle_tabs)
    page=QWidget();layout=QVBoxLayout(page);w.export_summary=QLabel();w.export_summary.setWordWrap(True);w.export_summary.setObjectName('exportSummary');layout.addWidget(w.export_summary)
    layout.addWidget(exportbox);w.include_voice=QCheckBox('Ghép giọng Việt đã tạo');w.include_voice.setToolTip('Bỏ chọn để xuất với tiếng video theo thiết lập âm gốc.');layout.addWidget(w.include_voice)
    w.include_voice.toggled.connect(w.export_voice_changed)
    w.export_btn=w.button('Xuất toàn bộ video…',w.export_workflow,True);layout.addWidget(w.export_btn)
    advanced=Foldout('Tốc độ dựng và thời lượng');advanced.body_layout.addWidget(speedbox);layout.addWidget(advanced);layout.addStretch();w.workflow_stack.addWidget(scroll(page))
    w.workflow_stack.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Expanding)
    w.split.widget(2).setMinimumWidth(330);w.split.widget(2).setMaximumWidth(410)
    w.sample_btn=w.button('Xem thử 10 giây',w.render_preview)
    w.timeline_toggle=QPushButton('Dòng thời gian');w.timeline_toggle.setCheckable(True);w.timeline_toggle.toggled.connect(w.update_workspace_visibility)
    bar=QHBoxLayout();bar.addWidget(w.timeline_toggle);bar.addStretch();bar.addWidget(w.sample_btn);outer.insertLayout(3,bar)
    w.effects_summary.setParent(w);w.effects_summary.hide()
    w.stage_index=0;w.preview_focused=False;w._export_voice_manual=False
    w.update_workspace_visibility();w.refresh_workflow()
