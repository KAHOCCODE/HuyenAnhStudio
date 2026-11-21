"""Output-space artwork: never mirrored with the source video."""
import math
import re
import uuid
from pathlib import Path

SIDEBAR = dict(enabled=False, side='right', width=22., color='#131B2D')
ICONS = {'heart':'Trái tim', 'star':'Ngôi sao', 'play':'Nút phát', 'music':'Nốt nhạc', 'info':'Thông tin'}
TEXT_PRESETS = {
    'clean':dict(color='#FFFFFF',outline_color='#101827',outline=2.,shadow=2.,background=False,accent=False,bold=True),
    'notice':dict(color='#FF303F',outline_color='#101827',outline=0.,shadow=0.,background=False,accent=True,bold=False),
    'gold':dict(color='#FFE4A0',outline_color='#3A2413',outline=2.,shadow=3.,background=True,accent=True,bold=True),
    'label':dict(color='#FFFFFF',outline_color='#101827',outline=0.,shadow=0.,background=True,accent=True,bold=True),
    'neon':dict(color='#85FFF0',outline_color='#243660',outline=3.,shadow=4.,background=False,accent=False,bold=True),
}
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
           accent_color='#FF303F',radius=14.,**TEXT_PRESETS[preset])
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
        box=rect.adjusted(pad,pad,-pad,-pad);font=QFont(v['font']);font.setPixelSize(max(1,round(v['size']*scale)));font.setBold(v['bold'])
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
        if v['shadow']:
            painter.save();painter.translate(v['shadow']*scale,v['shadow']*scale);painter.fillPath(path,QColor(0,0,0,150));painter.restore()
        if v['outline']:
            painter.setPen(QPen(QColor(v['outline_color']),2*v['outline']*scale,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));painter.setBrush(Qt.NoBrush);painter.drawPath(path)
        painter.fillPath(path,QColor(v['color']))
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
