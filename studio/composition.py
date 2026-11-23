"""Output-space artwork: never mirrored with the source video."""
import math
import re
import uuid
from pathlib import Path

SIDEBAR = dict(enabled=False, side='right', width=22., color='#131B2D')
ICONS = {'heart':'Trái tim', 'star':'Ngôi sao', 'play':'Nút phát', 'music':'Nốt nhạc', 'info':'Thông tin'}
TEXT_EFFECT_DEFAULTS = dict(fill_mode='solid',gradient_color='#FFFFFF',glow=0.,glow_color='#85FFF0',
                            depth=0.,depth_color='#172236',outer_outline=0.,outer_color='#101827',
                            tracking=0.,italic=False)
TEXT_PRESETS = {
    'clean':dict(color='#FFFFFF',outline_color='#101827',outline=2.,shadow=2.,background=False,accent=False,bold=True),
    'notice':dict(color='#FF303F',outline_color='#101827',outline=0.,shadow=0.,background=False,accent=True,bold=False),
    'gold':dict(font='Arial',color='#FFF1B8',outline_color='#FFF3C7',outline=1.,shadow=5.,background=False,accent=False,bold=True,
                fill_mode='metal',gradient_color='#B96B15',outer_outline=3.,outer_color='#50301C',depth=5.,depth_color='#704011',size=70.),
    'label':dict(color='#FFFFFF',outline_color='#101827',outline=0.,shadow=0.,background=True,accent=True,bold=True),
    'neon':dict(font='Arial',color='#E7FFFB',outline_color='#64FFE0',outline=1.5,shadow=0.,background=False,accent=False,bold=True,
                glow=22.,glow_color='#27E5C3',outer_outline=1.,outer_color='#168E9B',size=64.),
    'cinema':dict(color='#FFF7DD',outline_color='#5A3F25',outline=1.,shadow=6.,background=False,accent=False,bold=True,
                  font='Georgia',fill_mode='gradient',gradient_color='#C7A579',tracking=2.,size=64.),
    'comic':dict(font='Arial',color='#FFF7AC',outline_color='#352041',outline=4.,shadow=4.,background=False,accent=False,bold=True,
                 fill_mode='gradient',gradient_color='#FF9F32',outer_outline=2.,outer_color='#FFFFFF',depth=8.,depth_color='#AB244D',italic=True,size=68.),
    'ice':dict(font='Arial',color='#FFFFFF',outline_color='#E5FCFF',outline=1.,shadow=4.,background=False,accent=False,bold=True,
               fill_mode='gradient',gradient_color='#4CBEEB',outer_outline=3.,outer_color='#1D528A',depth=4.,depth_color='#163B68',size=68.),
    'rose':dict(font='Arial',color='#FFF1FA',outline_color='#FFFFFF',outline=1.5,shadow=3.,background=False,accent=False,bold=True,
                fill_mode='gradient',gradient_color='#F270BA',outer_outline=2.,outer_color='#8C3673',glow=14.,glow_color='#F478CF',size=64.),
}
TEXT_PRESET_LABELS = {'clean':'Trắng có viền','notice':'Thông báo vạch đỏ','gold':'Vàng kim nổi khối',
                      'label':'Nhãn nền tối','neon':'Neon xanh ngọc','cinema':'Tiêu đề điện ảnh',
                      'comic':'Truyện tranh','ice':'Pha lê xanh','rose':'Hồng ánh sáng'}


def text_preset(key):
    """Reset every effect when changing styles, including effects absent in old files."""
    return dict(TEXT_EFFECT_DEFAULTS,**TEXT_PRESETS[key])
SUBTITLE_PRESETS = [
    ('Trắng · viền đen',dict(color='#FFFFFF',outline_color='#101010',outline=3.,shadow=2.,box=False,bold=True)),
    ('Vàng · viền đen',dict(color='#FFE16A',outline_color='#151019',outline=3.,shadow=2.,box=False,bold=True)),
    ('Trắng · nền tối',dict(color='#FFFFFF',outline_color='#121C2B',outline=5.,shadow=0.,box=True,bold=True)),
    ('Điện ảnh · trắng ngà',dict(color='#FFF5DF',outline_color='#181818',outline=1.5,shadow=2.,box=False,bold=False)),
    ('Xanh ngọc · viền tím',dict(color='#A4FFF3',outline_color='#30214E',outline=3.,shadow=2.,box=False,bold=True)),
    ('Hồng nhạt · nền tím',dict(color='#FFE3F0',outline_color='#302038',outline=5.,shadow=1.,box=True,bold=True)),
]


def sidebar_settings(value):
    if not isinstance(value,dict) or set(value)-set(SIDEBAR):raise ValueError('Thiết lập dải bên không hợp lệ.')
    v=dict(SIDEBAR,**value)
    if not isinstance(v['enabled'],bool) or v['side'] not in ('left','right'):raise ValueError('Vị trí dải bên không hợp lệ.')
    number(v['width'],10,40);color(v['color'])
    return v


def color(value):
    if not isinstance(value,str) or not re.fullmatch('#[0-9a-fA-F]{6}',value):raise ValueError('Màu phải có dạng #RRGGBB.')


def number(value,low,high):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:raise ValueError('Thông số lớp trang trí nằm ngoài giới hạn.')


def new_layer(kind='text',duration=1,preset='clean'):
    v=dict(id=uuid.uuid4().hex[:12],kind=kind,name='Chữ mới',enabled=True,start=0.,end=max(.001,duration),
           x=4.,y=5.,w=40.,h=16.,text='Tên kênh',image='',icon='heart',font='Arial',size=40.,
           align='left',opacity=1.,background_color='#162338',background_opacity=.8,
           accent_color='#FF303F',radius=14.)
    v.update(text_preset(preset))
    if preset=='notice':v.update(name='Thông báo có vạch dọc',text='Phim được làm bởi AI\nKhán giả trên 18+',w=38.,h=12.,size=32.)
    if kind=='image':v.update(name='Logo kênh',text='',w=14.,h=18.)
    if kind=='icon':v.update(name='Biểu tượng',text='',w=8.,h=12.,color='#FF527C')
    return v


def validate_layer(v,duration):
    if not isinstance(v,dict) or set(v)-set(new_layer()):raise ValueError('Lớp trang trí chứa mục không hợp lệ.')
    if v.get('kind') not in ('text','image','icon') or v.get('align') not in ('left','center','right') or v.get('icon') not in ICONS:raise ValueError('Loại lớp trang trí không hợp lệ.')
    for key in ('enabled','bold','background','accent'):
        if not isinstance(v.get(key),bool):raise ValueError('Trạng thái lớp trang trí không hợp lệ.')
    for key in ('id','name','text','image','font'):
        if not isinstance(v.get(key),str):raise ValueError('Nội dung lớp trang trí không hợp lệ.')
    if not v['id'] or any(len(v[k])>10000 for k in ('name','text','image','font')):raise ValueError('Nội dung lớp quá dài.')
    for key in ('x','y'):number(v.get(key),0,99.9)
    for key in ('w','h'):number(v.get(key),.1,100)
    if v['x']+v['w']>100.01 or v['y']+v['h']>100.01:raise ValueError('Lớp trang trí nằm ngoài khung xuất.')
    for key in ('start','end'):number(v.get(key),0,duration if duration else 1e8)
    if v['start']>=v['end']:raise ValueError('Mốc kết thúc phải sau mốc bắt đầu.')
    for key in ('opacity','background_opacity'):number(v.get(key),0,1)
    number(v.get('size'),8,240);number(v.get('outline'),0,12);number(v.get('shadow'),0,16);number(v.get('radius'),0,60)
    for key in ('color','outline_color','background_color','accent_color'):color(v.get(key))
    if v.get('fill_mode','solid') not in ('solid','gradient','metal'):
        raise ValueError('Kiểu tô chữ không hợp lệ.')
    if not isinstance(v.get('italic',False),bool):raise ValueError('Kiểu chữ nghiêng không hợp lệ.')
    for key,high in [('glow',36),('depth',16),('outer_outline',12),('tracking',12)]:
        number(v.get(key,TEXT_EFFECT_DEFAULTS[key]),0,high)
    for key in ('gradient_color','glow_color','depth_color','outer_color'):
        color(v.get(key,TEXT_EFFECT_DEFAULTS[key]))


def validate_composition(p,files=False):
    sidebar_settings(p.sidebar)
    if p.mask.get('mode') not in ('blur','gblur','mosaic','solid'):raise ValueError('Kiểu vùng che không hợp lệ.')
    number(p.mask.get('strength',20),1,40)
    if 'outline_color' in p.style:color(p.style['outline_color'])
    number(p.style.get('spacing',0),0,8);number(p.style.get('fade',0),0,500)
    if not isinstance(p.overlays,list) or len(p.overlays)>40:raise ValueError('Tối đa 40 lớp chữ / logo / biểu tượng.')
    ids=set()
    for v in p.overlays:
        validate_layer(v,p.duration)
        if v['id'] in ids:raise ValueError('ID lớp trang trí bị trùng.')
        ids.add(v['id'])
        if files and v['enabled'] and v['kind']=='image' and not Path(v['image']).is_file():raise ValueError('Không tìm thấy logo: '+v['image']+'. Mở bảng Chữ / logo để chọn lại ảnh.')


def render_needed(p):
    return bool(p.video_effects.get('enabled') or p.sidebar.get('enabled') or any(v.get('enabled') for v in p.overlays)
                or p.mask.get('mode') in ('gblur','mosaic') and p.mask.get('enabled')
                or any(r.get('mode') in ('gblur','mosaic') and r.get('enabled',True) for r in p.screen_regions)
                or p.style.get('decorated'))


def subtitle_area(p,w,h):
    """Source-independent subtitle coordinates, excluding a reserved side panel."""
    bar=sidebar_settings(p.sidebar)
    content_w=max(2,int(w*(1-bar['width']/100))//2*2) if bar['enabled'] else w
    origin_x=w-content_w if bar['enabled'] and bar['side']=='left' else 0
    return origin_x,content_w,h


def layer_rect(v,w,h):
    return (w*v['x']/100,h*v['y']/100,w*v['w']/100,h*v['h']/100)


def paint_text(painter,path,v,scale):
    """Use the same vector effects for live preview and rasterized export artwork."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor,QLinearGradient,QPen
    glow=v.get('glow',0.)
    outer=v.get('outer_outline',0.)
    outline=v['outline']
    if glow:
        for step in range(8,0,-1):
            halo=QColor(v.get('glow_color',TEXT_EFFECT_DEFAULTS['glow_color']))
            halo.setAlphaF(.025+.07*(1-step/8))
            width=2*(outline+outer+glow*step/8)*scale
            painter.strokePath(path,QPen(halo,width,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    if v['shadow']:
        painter.save()
        painter.translate(v['shadow']*scale,v['shadow']*scale)
        painter.fillPath(path,QColor(0,0,0,150))
        painter.restore()
    depth=v.get('depth',0.)
    if depth:
        for step in range(math.ceil(depth),0,-1):
            offset=min(step,depth)*scale
            painter.save()
            painter.translate(offset,offset)
            painter.fillPath(path,QColor(v.get('depth_color',TEXT_EFFECT_DEFAULTS['depth_color'])))
            painter.restore()
    if outer:
        painter.strokePath(path,QPen(QColor(v.get('outer_color',TEXT_EFFECT_DEFAULTS['outer_color'])),
                                     2*(outline+outer)*scale,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    if outline:
        painter.strokePath(path,QPen(QColor(v['outline_color']),2*outline*scale,
                                     Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    fill=QColor(v['color'])
    mode=v.get('fill_mode','solid')
    if mode!='solid' and not path.isEmpty():
        bounds=path.boundingRect()
        gradient=QLinearGradient(bounds.left(),bounds.top(),bounds.left(),bounds.bottom())
        bottom=QColor(v.get('gradient_color',TEXT_EFFECT_DEFAULTS['gradient_color']))
        if mode=='metal':
            stops=[(0,fill.lighter(120)),(.3,fill),(.48,fill.lighter(140)),
                   (.53,bottom),(.8,fill),(1,bottom.lighter(120))]
        else:stops=[(0,fill),(1,bottom)]
        for position,color_value in stops:gradient.setColorAt(position,color_value)
        fill=gradient
    painter.fillPath(path,fill)


def draw_layer(painter,v,w,h):
    from PySide6.QtCore import QRectF,Qt,QPointF
    from PySide6.QtGui import QColor,QFont,QTextLayout,QTextOption,QPainterPath,QPen,QImageReader,QPolygonF
    rect=QRectF(*layer_rect(v,w,h));scale=h/1080
    painter.save();painter.setOpacity(v['opacity']);painter.setClipRect(rect)
    if v['background']:
        c=QColor(v['background_color']);c.setAlphaF(v['background_opacity'])
        painter.setPen(Qt.NoPen);painter.setBrush(c);painter.drawRoundedRect(rect,v['radius']*scale,v['radius']*scale)
    if v['accent']:
        painter.fillRect(QRectF(rect.x(),rect.y(),max(2,5*scale),rect.height()),QColor(v['accent_color']))
    if v['kind']=='image':
        reader=QImageReader(v['image']);reader.setAutoTransform(True)
        # Decode only the needed logo dimensions, bounding memory for very large images.
        size=reader.size()
        if size.isValid():reader.setScaledSize(size.scaled(max(1,int(rect.width())),max(1,int(rect.height())),Qt.KeepAspectRatio))
        image=reader.read()
        if image.isNull():painter.restore();raise ValueError('Không đọc được logo: '+v['image'])
        size=image.size().scaled(max(1,int(rect.width())),max(1,int(rect.height())),Qt.KeepAspectRatio)
        dest=QRectF(rect.center().x()-size.width()/2,rect.center().y()-size.height()/2,size.width(),size.height())
        painter.drawImage(dest,image)
    elif v['kind']=='icon':
        painter.translate(rect.x(),rect.y());painter.scale(rect.width()/100,rect.height()/100)
        painter.setPen(Qt.NoPen);painter.setBrush(QColor(v['color']));path=QPainterPath();icon=v['icon']
        if icon=='heart':
            path.moveTo(50,90);path.cubicTo(-40,35,15,-8,50,25);path.cubicTo(85,-8,140,35,50,90);painter.drawPath(path)
        elif icon=='star':
            points=[QPointF(50+math.sin(i*math.pi/5)*(47 if i%2==0 else 21),50-math.cos(i*math.pi/5)*(47 if i%2==0 else 21)) for i in range(10)]
            painter.drawPolygon(QPolygonF(points))
        elif icon=='play':painter.drawPolygon(QPolygonF([QPointF(18,8),QPointF(92,50),QPointF(18,92)]))
        elif icon=='music':
            painter.drawEllipse(QRectF(8,66,30,25));painter.drawEllipse(QRectF(59,52,30,25));painter.fillRect(QRectF(31,12,7,66),QColor(v['color']));painter.fillRect(QRectF(82,4,7,61),QColor(v['color']));painter.drawPolygon(QPolygonF([QPointF(31,12),QPointF(89,4),QPointF(89,19),QPointF(31,27)]))
        else:
            painter.drawEllipse(QRectF(3,3,94,94));painter.setPen(QPen(QColor(v['background_color']),10));painter.drawLine(QPointF(50,43),QPointF(50,77));painter.drawPoint(QPointF(50,25))
    else:
        pad=(14 if v['background'] or v['accent'] else 2)*scale
        if any(v.get(key,0) for key in ('glow','depth','outer_outline')):
            pad=max(pad,(2+v['outline']+v.get('outer_outline',0)+v.get('glow',0)
                         +v.get('depth',0)+v['shadow'])*scale)
        box=rect.adjusted(pad,pad,-pad,-pad);font=QFont(v['font']);font.setPixelSize(max(1,round(v['size']*scale)));font.setBold(v['bold'])
        font.setItalic(v.get('italic',False))
        if v.get('tracking',0):font.setLetterSpacing(QFont.AbsoluteSpacing,v['tracking']*scale)
        y=box.y();path=QPainterPath()
        for paragraph in v['text'].split('\n'):
            layout=QTextLayout(paragraph,font);option=QTextOption();option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere);layout.setTextOption(option);layout.beginLayout()
            while True:
                line=layout.createLine()
                if not line.isValid():break
                line.setLineWidth(max(1,box.width()));lw=line.naturalTextWidth()
                x=box.x()+({'left':0,'center':(box.width()-lw)/2,'right':box.width()-lw}[v['align']])
                # Glyph runs preserve Vietnamese shaping and wrapping from QTextLayout.
                for run in line.glyphRuns():
                    raw=run.rawFont()
                    for glyph,point in zip(run.glyphIndexes(),run.positions()):
                        g=raw.pathForGlyph(glyph);g.translate(x+point.x(),y+point.y());path.addPath(g)
                y+=line.height()*1.12
            layout.endLayout()
        paint_text(painter,path,v,scale)
    painter.restore()


def prepare_layers(folder,p):
    """Rasterize static artwork once, merge consecutive layers sharing the same timing."""
    from PySide6.QtCore import Qt,QRectF
    from PySide6.QtGui import QGuiApplication,QImage,QPainter
    from .video_effects import output_size
    validate_composition(p,files=True)
    layers=[v for v in p.overlays if v['enabled']]
    if not layers:return []
    if QGuiApplication.instance() is None:raise RuntimeError('Cần khởi tạo giao diện Qt trước khi dựng chữ / logo.')
    w,h=output_size(p);groups=[]
    for v in layers:
        if not groups or (groups[-1][0],groups[-1][1])!=(v['start'],v['end']):groups.append([v['start'],v['end'],[]])
        groups[-1][2].append(v)
    results=[]
    for i,(start,end,items) in enumerate(groups):
        bounds=QRectF()
        for v in items:bounds=bounds.united(QRectF(*layer_rect(v,w,h)))
        bounds=bounds.toAlignedRect().intersected(QRectF(0,0,w,h).toRect())
        image=QImage(bounds.size(),QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
        painter=QPainter(image);painter.setRenderHint(QPainter.Antialiasing);painter.setRenderHint(QPainter.SmoothPixmapTransform);painter.translate(-bounds.x(),-bounds.y())
        try:
            for v in items:draw_layer(painter,v,w,h)
        finally:painter.end()
        name=f'artwork-{i}.png'
        if not image.save(str(Path(folder)/name)):raise RuntimeError('Không lưu được lớp chữ / logo tạm.')
        results.append(dict(file=name,x=bounds.x(),y=bounds.y(),start=start,end=end))
    return results


def artwork_filter(source,assets):
    parts=[]
    for i,v in enumerate(assets):
        target=f'[art{i}]';image=f'[artimg{i}]'
        parts.append(f"movie=filename='{v['file']}',setpts=PTS-STARTPTS{image}")
        parts.append(f"{source}{image}overlay=x={v['x']}:y={v['y']}:eof_action=repeat:repeatlast=1:enable='gte(t,{v['start']:.6f})*lt(t,{v['end']:.6f})'{target}")
        source=target
    return parts,source
